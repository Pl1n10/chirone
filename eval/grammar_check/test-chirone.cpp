// Derived from llama.cpp tests/test-grammar-integration.cpp (MIT). Drop into llama.cpp/tests/,
// add `llama_build(test-chirone.cpp)` to tests/CMakeLists.txt, build target test-chirone.
#ifdef NDEBUG
#undef NDEBUG
#endif

#include "json-schema-to-grammar.h"

#include "../src/unicode.h"
#include "../src/llama-grammar.h"

#include "json.h"

#include <cassert>
#include <string>
#include <vector>

using json = common_json;

static llama_grammar * build_grammar_with_root(const std::string & grammar_str, const char * grammar_root) {
    return llama_grammar_init_impl(nullptr, grammar_str.c_str(), grammar_root, false, nullptr, 0, nullptr, 0);
}

static llama_grammar * build_grammar(const std::string & grammar_str) {
    return build_grammar_with_root(grammar_str, "root");
}

static bool test_build_grammar_fails(const std::string & grammar_str) {
    fprintf(stderr, "⚫ Testing failure for grammar: %s\n", grammar_str.c_str());
    bool grammar_fails = false;
    llama_grammar * grammar = build_grammar(grammar_str);
    if (grammar != nullptr) {
        fprintf(stderr, "  ❌ Expected build failure, but succeeded\n");
    } else {
        grammar_fails = true;
        fprintf(stdout, "  ✅︎\n");
    }
    return grammar_fails;
}

struct token_and_piece {
    llama_token token;
    std::string piece;
};

// token() encodes a 32-bit ID as 5 bytes: a 0xff marker followed by the ID in big-endian order.
static std::string token(llama_token id) {
    return std::string{
        static_cast<char>(0xff),
        static_cast<char>((id >> 24) & 0xff),
        static_cast<char>((id >> 16) & 0xff),
        static_cast<char>((id >> 8) & 0xff),
        static_cast<char>(id & 0xff)
    };
}

// parse_tokens() parses the token encodes above and UTF-8 text.
static std::vector<token_and_piece> parse_tokens(const std::string & input) {
    std::vector<token_and_piece> result;
    result.reserve(input.size());
    size_t offset = 0;
    while (offset < input.size()) {
        try {
            if (static_cast<unsigned char>(input[offset]) == 0xff) {
                if (offset + 5 > input.size()) {
                    throw std::runtime_error("not enough bytes for token id");
                }
                uint32_t val =
                    (static_cast<unsigned char>(input[offset + 1]) << 24) |
                    (static_cast<unsigned char>(input[offset + 2]) << 16) |
                    (static_cast<unsigned char>(input[offset + 3]) << 8)  |
                    (static_cast<unsigned char>(input[offset + 4]));
                auto piece = "<[" + std::to_string(val) + "]>";
                result.push_back({static_cast<llama_token>(val), piece});
                offset += 5;
            } else {
                uint32_t cpt = unicode_cpt_from_utf8(input, offset);
                result.push_back({0, unicode_cpt_to_utf8(cpt)});
            }
        } catch (const std::invalid_argument & /*ex*/) {
            // Silently ignore invalid UTF-8 input to avoid leaking the exception beyond llama_tokenize
            ++offset;
            result.push_back({0, unicode_cpt_to_utf8(0xFFFD)}); // replacement character
        }
    }
    return result;
}

static bool match_string(const std::string & input, llama_grammar * grammar) {
    const auto parsed = parse_tokens(input);

    auto & stacks_cur = llama_grammar_get_stacks(grammar);

    for (const auto & in : parsed) {
        try {
            llama_grammar_accept_token(*grammar, in.token, in.piece);
        } catch (const std::runtime_error & /*e*/) {
            // normally this shouldn't get hit because of llama_grammar_apply
            return false;
        }

        if (stacks_cur.empty()) {
            // no stacks means that the grammar failed to match at this point
            return false;
        }
    }

    for (const auto & stack : stacks_cur) {
        if (stack.empty()) {
            // An empty stack means that the grammar has been completed
            return true;
        }
    }

    return false;
}

#include <fstream>
#include <sstream>

// usage: test-chirone cases.json
// cases.json: [{"name":..., "schema":{...}, "pass":[...], "fail":[...]}]
int main(int argc, char ** argv) {
    std::ifstream f(argv[1]);
    std::stringstream ss; ss << f.rdbuf();
    auto cases = common_json::parse(ss.str());
    int failures = 0;
    for (auto & c : cases) {
        std::string g;
        try { g = json_schema_to_grammar(c["schema"]); }
        catch (const std::exception & e) { printf("CONVERT FAIL %s: %s\n", c["name"].template get<std::string>().c_str(), e.what()); failures++; continue; }
        auto * grammar = build_grammar(g);
        if (!grammar) { printf("BUILD FAIL %s\n%s\n", c["name"].template get<std::string>().c_str(), g.c_str()); failures++; continue; }
        const llama_grammar_stacks org = llama_grammar_get_stacks(grammar);
        for (auto & s : c["pass"]) {
            llama_grammar_get_stacks(grammar) = org;
            if (!match_string(s.template get<std::string>(), grammar)) { printf("SHOULD PASS [%s] %s\n", c["name"].template get<std::string>().c_str(), s.template get<std::string>().c_str()); failures++; }
        }
        for (auto & s : c["fail"]) {
            llama_grammar_get_stacks(grammar) = org;
            if (match_string(s.template get<std::string>(), grammar)) { printf("SHOULD FAIL [%s] %s\n", c["name"].template get<std::string>().c_str(), s.template get<std::string>().c_str()); failures++; }
        }
        printf("ok %s (%zu grammar bytes)\n", c["name"].template get<std::string>().c_str(), g.size());
        llama_grammar_free_impl(grammar);
    }
    printf("failures: %d\n", failures);
    return failures ? 1 : 0;
}
