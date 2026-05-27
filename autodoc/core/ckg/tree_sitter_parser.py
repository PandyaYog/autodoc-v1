import tree_sitter
import tree_sitter_javascript
import tree_sitter_typescript

def get_javascript_parser() -> tree_sitter.Parser:
    """Returns a tree-sitter parser configured for JavaScript."""
    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_javascript.language()))
    return parser

def get_typescript_parser() -> tree_sitter.Parser:
    """Returns a tree-sitter parser configured for TypeScript."""
    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_typescript.language_typescript()))
    return parser

def get_tsx_parser() -> tree_sitter.Parser:
    """Returns a tree-sitter parser configured for TSX (React TypeScript)."""
    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_typescript.language_tsx()))
    return parser
