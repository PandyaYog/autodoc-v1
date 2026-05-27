import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

def _get_node_text(node, source_code: bytes) -> str:
    """Extracts the text of a node from the source code bytes."""
    if node is None:
        return ""
    return source_code[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

class ReactVisitor:
    """
    Visits a Tree-sitter AST for JavaScript/TypeScript to extract structural information,
    focusing on React components, hooks, standard classes, functions, and imports.
    """
    def __init__(self, file_path: str, source_code: bytes):
        self.file_path = file_path
        self.source_code = source_code
        self.imports: List[Dict[str, Any]] = []
        self.classes: List[Dict[str, Any]] = []
        self.functions: List[Dict[str, Any]] = []
        self.react_components: List[Dict[str, Any]] = []
        self.react_hooks: List[Dict[str, Any]] = []
        self.calls: List[Dict[str, Any]] = []
        
        # We don't track top level code exhaustively for JS yet
        self.top_level_code: List[Dict[str, Any]] = []

    def visit(self, tree):
        root = tree.root_node
        self._traverse_top_level(root)

    def _traverse_top_level(self, root_node):
        for child in root_node.children:
            if child.type == 'import_statement':
                self._handle_import(child)
            elif child.type == 'export_statement':
                self._traverse_top_level(child)
            elif child.type == 'class_declaration':
                self._handle_class(child)
            elif child.type == 'function_declaration':
                self._handle_function_or_component(child, is_top_level=True)
            elif child.type in ('lexical_declaration', 'variable_declaration'):
                self._handle_variable_declaration(child)
            elif child.type == 'expression_statement':
                pass # Can handle top level calls here if needed

    def _handle_import(self, node):
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        source_module = ""
        
        for child in node.children:
            if child.type == 'string':
                source_module = _get_node_text(child, self.source_code).strip("'\"")
        
        # Simple extraction for now: we capture the whole statement 
        # as a single 'from' import for simplicity in resolver.
        snippet = _get_node_text(node, self.source_code)
        
        # For actual aliases, one would traverse import_clause -> named_imports.
        # We'll store a generic representation.
        self.imports.append({
            "type": "from",
            "module": source_module,
            "level": 0,
            "name": "*", # Placeholder for everything imported
            "alias": None,
            "start_line": start_line,
            "end_line": end_line,
            "code_snippet": snippet
        })

    def _handle_class(self, node):
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        name_node = node.child_by_field_name('name')
        name = _get_node_text(name_node, self.source_code) if name_node else "AnonymousClass"
        
        # Simplified class extraction
        class_data = {
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "docstring": None,
            "bases": [],
            "methods": [],
            "code_snippet": _get_node_text(node, self.source_code),
            "access_modifier": "public",
            "used_names": []
        }
        
        # Check if it extends React.Component
        is_react_class = False
        heritage = node.child_by_field_name('heritage')
        if heritage:
            heritage_text = _get_node_text(heritage, self.source_code)
            if "Component" in heritage_text:
                is_react_class = True
        
        body = node.child_by_field_name('body')
        if body:
            for child in body.children:
                if child.type == 'method_definition':
                    m_name_node = child.child_by_field_name('name')
                    m_name = _get_node_text(m_name_node, self.source_code)
                    m_start = child.start_point[0] + 1
                    m_end = child.end_point[0] + 1
                    class_data["methods"].append({
                        "name": m_name,
                        "start_line": m_start,
                        "end_line": m_end,
                        "docstring": None,
                        "signature": f"{m_name}()",
                        "is_method": True,
                        "access_modifier": "public",
                        "code_snippet": _get_node_text(child, self.source_code),
                        "used_names": []
                    })
                    if m_name == 'render':
                        is_react_class = True

        if is_react_class:
            class_data["props"] = []
            class_data["hooks_used"] = []
            class_data["renders_components"] = self._extract_jsx_tags(node)
            self.react_components.append(class_data)
        else:
            self.classes.append(class_data)

    def _handle_variable_declaration(self, node):
        # Handle const MyComp = () => {}
        for child in node.children:
            if child.type == 'variable_declarator':
                name_node = child.child_by_field_name('name')
                value_node = child.child_by_field_name('value')
                
                if value_node and value_node.type in ('arrow_function', 'function_expression'):
                    self._handle_function_or_component(value_node, is_top_level=True, override_name_node=name_node)

    def _handle_function_or_component(self, node, is_top_level=False, override_name_node=None):
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        name_node = override_name_node or node.child_by_field_name('name')
        name = _get_node_text(name_node, self.source_code) if name_node else "AnonymousFunction"
        
        is_react = False
        jsx_tags = self._extract_jsx_tags(node)
        if jsx_tags:
            is_react = True
        elif name and name[0].isupper():
            # Convention: React components are capitalized
            is_react = True

        is_hook = False
        if name.startswith("use") and len(name) > 3 and name[3].isupper():
            is_hook = True
            is_react = False # Hooks are distinct from components in our model

        func_data = {
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "docstring": None,
            "signature": f"function {name}()",
            "is_method": False,
            "access_modifier": "public",
            "code_snippet": _get_node_text(node, self.source_code),
            "used_names": []
        }

        if is_react:
            func_data["props"] = [] # Complex to extract accurately without full type checking
            func_data["hooks_used"] = self._extract_hooks_used(node)
            func_data["renders_components"] = jsx_tags
            self.react_components.append(func_data)
        elif is_hook:
            self.react_hooks.append(func_data)
        else:
            self.functions.append(func_data)

        # Track calls made inside the function
        calls = self._extract_calls(node)
        for call_name, c_line in calls:
            self.calls.append({
                "caller_type": "FUNCTION",
                "caller_name": name,
                "caller_lines": (start_line, end_line),
                "call_name": call_name,
                "line": c_line,
                "code_snippet": f"{call_name}()"
            })

    def _extract_jsx_tags(self, node) -> List[str]:
        tags = set()
        def walk(n):
            if n.type in ('jsx_element', 'jsx_self_closing_element'):
                open_tag = n.child_by_field_name('open_tag') if n.type == 'jsx_element' else n
                if open_tag:
                    name_node = open_tag.child_by_field_name('name')
                    if name_node:
                        tag_name = _get_node_text(name_node, self.source_code)
                        # Only collect capitalized tags (custom components)
                        if tag_name and tag_name[0].isupper():
                            tags.add(tag_name)
            for child in n.children:
                walk(child)
        walk(node)
        return list(tags)

    def _extract_hooks_used(self, node) -> List[str]:
        hooks = set()
        def walk(n):
            if n.type == 'call_expression':
                func_node = n.child_by_field_name('function')
                if func_node and func_node.type == 'identifier':
                    func_name = _get_node_text(func_node, self.source_code)
                    if func_name.startswith('use'):
                        hooks.add(func_name)
            for child in n.children:
                walk(child)
        walk(node)
        return list(hooks)

    def _extract_calls(self, node) -> List[Tuple[str, int]]:
        calls = []
        def walk(n):
            if n.type == 'call_expression':
                func_node = n.child_by_field_name('function')
                if func_node:
                    func_name = _get_node_text(func_node, self.source_code)
                    line = n.start_point[0] + 1
                    calls.append((func_name, line))
            for child in n.children:
                walk(child)
        walk(node)
        return calls

    def get_results(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "imports": self.imports,
            "classes": self.classes,
            "functions": self.functions,
            "react_components": self.react_components,
            "react_hooks": self.react_hooks,
            "calls": self.calls,
            "top_level_code": self.top_level_code,
        }
