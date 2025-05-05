import ast
import logging
from typing import List, Dict, Any, Optional, Tuple, Union

logger = logging.getLogger(__name__)

def _get_node_lines(node: ast.AST) -> Tuple[Optional[int], Optional[int]]:
    """Safely extracts start and end line numbers from an AST node."""
    start_line = getattr(node, 'lineno', None)
    end_line = getattr(node, 'end_lineno', None)
    return start_line, end_line

def _get_docstring(node: Union[ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Module]) -> Optional[str]:
    """Safely extracts the docstring from a node."""
    return ast.get_docstring(node, clean=True)

def _format_arg(arg: ast.arg) -> str:
    """Formats a single argument AST node into a string."""
    arg_str = arg.arg
    if arg.annotation:
        try:
            annotation_str = ast.unparse(arg.annotation).strip()
            arg_str += f": {annotation_str}"
        except Exception:
            logger.warning(f"Could not unparse annotation for argument '{arg.arg}'", exc_info=False)
            arg_str += ": ?"
    return arg_str

def _format_signature(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> str:
    """Formats the signature of a function/method node."""
    args = node.args
    signature_parts = []

    signature_parts.extend([_format_arg(arg) for arg in args.posonlyargs])
    if args.posonlyargs:
        signature_parts.append('/')

    num_args_with_defaults = len(args.defaults)
    num_regular_args = len(args.args)
    defaults_start_index = num_regular_args - num_args_with_defaults

    for i, arg in enumerate(args.args):
        arg_str = _format_arg(arg)
        if i >= defaults_start_index:
            try:
                default_str = ast.unparse(args.defaults[i - defaults_start_index]).strip()
                arg_str += f" = {default_str}"
            except Exception:
                 logger.warning(f"Could not unparse default value for argument '{arg.arg}'", exc_info=False)
                 arg_str += " = ?"
        signature_parts.append(arg_str)

    if args.vararg:
        signature_parts.append(f"*{_format_arg(args.vararg)}")

    if args.kwonlyargs:
        if not args.vararg:
             signature_parts.append('*')
        num_kwonly_with_defaults = len(args.kw_defaults)
        defaults_start_index_kw = len(args.kwonlyargs) - num_kwonly_with_defaults

        for i, arg in enumerate(args.kwonlyargs):
            arg_str = _format_arg(arg)
            default_val = args.kw_defaults[i]
            if default_val is not None:
                 try:
                    default_str = ast.unparse(default_val).strip()
                    arg_str += f" = {default_str}"
                 except Exception:
                    logger.warning(f"Could not unparse default value for kwonly argument '{arg.arg}'", exc_info=False)
                    arg_str += " = ?"
            signature_parts.append(arg_str)


    if args.kwarg:
        signature_parts.append(f"**{_format_arg(args.kwarg)}")

    return_annotation = ""
    if node.returns:
        try:
            return_annotation = f" -> {ast.unparse(node.returns).strip()}"
        except Exception:
            logger.warning(f"Could not unparse return annotation for function '{node.name}'", exc_info=False)
            return_annotation = " -> ?"

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(signature_parts)}){return_annotation}"

def _get_call_name(node: ast.Call) -> Optional[str]:
    """Tries to extract a simple name string for the function being called."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    elif isinstance(func, ast.Attribute):
        try:
            return ast.unparse(func).strip()
        except Exception:
            logger.debug(f"Could not unparse complex call target at line {node.lineno}", exc_info=False)
            return None
    return None

def _get_access_modifier(name: str) -> str:
    """Infers access modifier based on Python naming conventions."""
    if name.startswith("__") and not name.endswith("__"): # Exclude dunder methods
        return "private"
    elif name.startswith("_"):
        return "protected"
    else:
        return "public"


class ASTVisitor(ast.NodeVisitor):
    """
    Visits AST nodes of a Python file to extract structural information.

    Collects data about imports, classes, functions, calls, and top-level code
    without directly modifying the CKG.
    """

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.lines = source_code.splitlines()

        self.imports: List[Dict[str, Any]] = []
        self.classes: List[Dict[str, Any]] = []
        self.functions: List[Dict[str, Any]] = []
        self.calls: List[Dict[str, Any]] = []
        self.top_level_code: List[Dict[str, Any]] = []
        self.used_names: Dict[Tuple[int, int], List[str]] = {}
        self._current_context_stack: List[Tuple[str, str, Tuple[int, int]]] = []

    def _get_source_segment(self, node: ast.AST) -> Optional[str]:
        """Gets the original source code segment for a node."""
        try:
            return ast.get_source_segment(self.source_code, node, padded=False)
        except Exception:
            logger.warning(
                f"Could not get source segment for node type {type(node).__name__} at line {getattr(node, 'lineno', '?')}",
                exc_info=False)
            try:
                return ast.unparse(node)
            except Exception:
                return None

    def _add_used_name(self, name: str):
        """Adds a used name to the current context."""
        if self._current_context_stack:
            context_type, context_name, context_lines = self._current_context_stack[-1]
            if context_lines not in self.used_names:
                self.used_names[context_lines] = []
            if name not in self.used_names[context_lines]:
                self.used_names[context_lines].append(name)

    def visit(self, node):
        """Override visit to handle specific node types and track context."""
        method_name = f'visit_{node.__class__.__name__}'
        visitor_method = getattr(self, method_name, None)

        if visitor_method is not None:
            visitor_method(node)
        else:
            is_top_level = not self._current_context_stack
            top_level_code_types = (
                ast.Assign, ast.AnnAssign, ast.AugAssign,
                ast.Expr,
                ast.If, ast.For, ast.While, ast.With,
                ast.Try, ast.Raise, ast.Assert,
                ast.AsyncFor, ast.AsyncWith,
            )

            create_tl_node = False
            if is_top_level and isinstance(node, top_level_code_types):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Name):
                    logger.debug(f"Ignoring top-level bare name Expr: {node.value.id} at line {node.lineno}")
                    create_tl_node = False
                else:
                    create_tl_node = True

            if create_tl_node:
                start_line, end_line = _get_node_lines(node)
                if start_line is not None and end_line is not None:
                    snippet = self._get_source_segment(node)
                    name = f"top_level_code_L{start_line}-L{end_line}"
                    self.top_level_code.append({
                        "name": name,
                        "start_line": start_line,
                        "end_line": end_line,
                        "code_snippet": snippet,
                    })
                    self._current_context_stack.append(("TOP_LEVEL", name, (start_line, end_line)))
                    try:
                        self.generic_visit(node)
                    finally:
                        self._current_context_stack.pop()
                    return
            else:
                self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        start_line, end_line = _get_node_lines(node)
        for alias in node.names:
            self.imports.append({
                "type": "import",
                "module": None,
                "name": alias.name,
                "alias": alias.asname,
                "start_line": start_line,
                "end_line": end_line,
                "code_snippet": self._get_source_segment(node)
            })

    def visit_ImportFrom(self, node: ast.ImportFrom):
        start_line, end_line = _get_node_lines(node)
        module_name = node.module or ""
        level = node.level
        for alias in node.names:
            self.imports.append({
                "type": "from",
                "module": module_name,
                "level": level,
                "name": alias.name,
                "alias": alias.asname,
                "start_line": start_line,
                "end_line": end_line,
                "code_snippet": self._get_source_segment(node)
            })

    def visit_ClassDef(self, node: ast.ClassDef):
        start_line, end_line = _get_node_lines(node)
        docstring = _get_docstring(node)
        bases = [ast.unparse(b).strip() for b in node.bases if hasattr(ast, 'unparse')]
        keywords = {kw.arg: ast.unparse(kw.value).strip() for kw in node.keywords if kw.arg}
        decorator_list = [ast.unparse(d).strip() for d in node.decorator_list]

        class_data = {
            "name": node.name,
            "start_line": start_line,
            "end_line": end_line,
            "docstring": docstring,
            "bases": bases,
            "keywords": keywords,
            "decorators": decorator_list,
            "methods": [],
            "nested_classes": [],
            "class_variables": [],
            "code_snippet": self._get_source_segment(node),
            "access_modifier": _get_access_modifier(node.name),
        }

        self._current_context_stack.append(("CLASS", node.name, (start_line, end_line)))
        try:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_data = self._extract_function_data(item, is_method=True, class_name=node.name)
                    if method_data:
                        class_data["methods"].append(method_data)
                elif isinstance(item, ast.ClassDef):
                    nested_start, nested_end = _get_node_lines(item)
                    class_data["nested_classes"].append({
                        "name": item.name,
                        "start_line": nested_start,
                        "end_line": nested_end,
                    })
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            var_start, var_end = _get_node_lines(item)
                            class_data["class_variables"].append({
                                "name": target.id,
                                "start_line": var_start,
                                "end_line": var_end,
                                "code_snippet": self._get_source_segment(item)
                            })
                elif not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    self.visit(item)
        finally:
            self._current_context_stack.pop()
        self.classes.append(class_data)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node)

    def _handle_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]):
        is_top_level = not any(ctx[0] == "CLASS" for ctx in self._current_context_stack)
        if is_top_level:
            func_data = self._extract_function_data(node, is_method=False)
            if func_data:
                self.functions.append(func_data)
                self._current_context_stack.append(
                    ("FUNCTION", node.name, (func_data["start_line"], func_data["end_line"])))
                try:
                    self.generic_visit(node)
                finally:
                    self._current_context_stack.pop()


    def _extract_function_data(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], is_method: bool,
                               class_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        start_line, end_line = _get_node_lines(node)
        docstring = _get_docstring(node)
        signature = _format_signature(node)
        decorator_list = [ast.unparse(d).strip() for d in node.decorator_list]

        func_data = {
            "name": node.name,
            "start_line": start_line,
            "end_line": end_line,
            "docstring": docstring,
            "signature": signature,
            "decorators": decorator_list,
            "is_method": is_method,
            "class_name": class_name,
            "code_snippet": self._get_source_segment(node),
            "access_modifier": _get_access_modifier(node.name),
            "calls": [],
        }

        if is_method:
            self._current_context_stack.append(("FUNCTION", node.name, (start_line, end_line)))
            try:
                self.generic_visit(node)
            finally:
                self._current_context_stack.pop()

        return func_data

    def visit_Call(self, node: ast.Call):
        start_line, end_line = _get_node_lines(node)
        call_name = _get_call_name(node)

        caller_type = "FILE"
        caller_name = self.file_path
        caller_lines = (1, len(self.lines))

        if self._current_context_stack:
            caller_type, caller_name, caller_lines = self._current_context_stack[-1]

        if call_name:
            self.calls.append({
                "caller_type": caller_type,
                "caller_name": caller_name,
                "caller_lines": caller_lines,
                "call_name": call_name,
                "line": start_line,
                "code_snippet": self._get_source_segment(node),
            })
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        """Track names used within the current context."""
        if isinstance(node.ctx, ast.Load):
            self._add_used_name(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        """Track attribute access (e.g., module.function, obj.method)."""
        try:
            full_name = ast.unparse(node).strip()
            if isinstance(node.ctx, ast.Load):
                self._add_used_name(full_name)
        except Exception:
            if isinstance(node.ctx, ast.Load):
                self._add_used_name(node.attr)
        self.generic_visit(node)

    def get_results(self) -> Dict[str, Any]:
        """Returns all collected data."""
        linked_functions = []
        for func in self.functions:
            lines = (func["start_line"], func["end_line"])
            func["used_names"] = self.used_names.get(lines, [])
            linked_functions.append(func)

        linked_classes = []
        for cls in self.classes:
            cls_lines = (cls["start_line"], cls["end_line"])
            cls["used_names"] = self.used_names.get(cls_lines, [])
            linked_methods = []
            for method in cls["methods"]:
                method_lines = (method["start_line"], method["end_line"])
                method["used_names"] = self.used_names.get(method_lines, [])
                linked_methods.append(method)
            cls["methods"] = linked_methods
            linked_classes.append(cls)

        linked_top_level = []
        for tl in self.top_level_code:
            lines = (tl["start_line"], tl["end_line"])
            tl["used_names"] = self.used_names.get(lines, [])
            linked_top_level.append(tl)

        return {
            "file_path": self.file_path,
            "imports": self.imports,
            "classes": linked_classes,
            "functions": linked_functions,
            "calls": self.calls,
            "top_level_code": linked_top_level,
        }