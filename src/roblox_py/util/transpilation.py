import ast
import re
from typing_extensions import Self

# Refer to:
# https://docs.python.org/3/library/ast.html#abstract-grammar

toggle_ast = False;
toggle_line_of_code = False;
toggle_block_ids = False;

# Keep track of every block

builtin_attribute_functions = {
    "List": {
        "append": "ropy.append.list"
    },

    "Dict": {
        "setdefault": "ropy.setdefault.dict",
    },

    "Set": {
        "add": "ropy.add.set",
    }
}

builtin_functions = {
    "len": "ropy.len",		            # OK
    "help": "",                         # OK
    "range": "ropy.range",	            # OK
    "discriminate_tables": {
        "set": "ropy.set",		        # OK
        "all": "ropy.all",		        # OK
    }
}

class CodeBlock:
    def __init__(self, block_id: str, type: str, variables: list[str], children: list[Self], parent: Self | None = None):
        self.block_id: str = block_id;
        self.type: str = type;
        self.variables: str = variables;
        self.children: list[Self] = children;
        self.parent: Self | None = parent;
        self.line: str = "";
        self.deep_variables: list[str] = [];
        self.node: ast.FunctionDef = "";

    def get_function(self) -> Self:
        if self.parent is None: return self;

        if self.type == "function": return self;

        ancestor = self.parent;

        while ancestor.block_id != "0" and ancestor.type != "function":
            ancestor = ancestor.parent

        return ancestor;

    def add_variable(self, variable: str) -> None | str: # "surface" | "deep"
        function_block = self.get_function();
        
        if variable in function_block.variables or variable in function_block.deep_variables: return None;

        if function_block == self:
            function_block.variables.append(variable);
            return "surface"
        else:
            function_block.deep_variables.append(variable);
            return "deep"

    def add_child(self, type: str, node: ast.FunctionDef | None = None) -> Self: # Preferred over __init__
        # New id is the self.block_id + "." + the next available int
        new_id = self.block_id + "." + str(len(self.children));

        # Create a new block
        new_block = CodeBlock(new_id, type, [], [], self);

        # If node is not None, set the node of the block
        if node is not None: new_block.node = node;

        # Add the new block to the children of the current block
        self.children.append(new_block);

        return new_block;
    
    def get_offset(self, relative_offset: int = 0) -> str:
        # Get amount of periods in the block_id
        # Multiply " " by this amount
        level = len(self.block_id.split(".")) - 1 + relative_offset

        # kirby = ["(>'-')>","<('-'<)","^('-')^","v('-')v","(>'-')>","(^-^)"]; 
        # return "--[[" + " ".join(kirby[i % len(kirby)] for i in range(level)) + "]]"
        
        spaces = 1;
        char = "\t";

        offset = level * spaces * char;

        return offset

top_block = CodeBlock("0", "top", [], []);

def get_function_block_by_name(name: str, within_block: CodeBlock) -> CodeBlock:
    # Loop through children of within_block, find the function with the same name
    for child in within_block.children:
        if child.type == "function" and child.node.name == name:
            return child;
    
    return None;

def initialise_string(node: any, block: CodeBlock) -> str:
    result = "";

    if toggle_ast:
        result = result + "--[[" + node.__class__.__name__ + "]]"

    if toggle_block_ids:
        result = result + "--[[ BlockId: " + block["block_id"] + "]]";
    
    return result;

def process_builtin_attribute_function(node: ast.Call, block: CodeBlock) -> str | None:
    # If I knew how to obtain the attributee node from the given node, I could do this
    # builtin_list = builtin_attribute_functions;
    # nodeType = "";
    # b = node.func.value;
    # print(isinstance(b, ast.Dict), isinstance(b, ast.Set), isinstance(b, ast.List), isinstance(b, ast.Tuple))
    # if isinstance(node.func, ast.Dict):
    #     builtin_list = builtin_attribute_functions["Dict"];
    #     nodeType = "Dict";
    # elif isinstance(node.func, ast.Set):
    #     builtin_list = builtin_attribute_functions["Set"];
    #     nodeType = "Set";
    # elif isinstance(node.func, ast.List):
    #     builtin_list = builtin_attribute_functions["List"];
    #     nodeType = "List";
    # elif isinstance(node.func, ast.Tuple):
    #     builtin_list = builtin_attribute_functions["Tuple"];
    #     nodeType = "Tuple";
    # else:
    #     return None;

    # print(node.func.attr)

    # if not node.func.attr in builtin_list:
    #     return None;

    # result = builtin_list[node.func.attr];

    nodeType = ""
    
    # Loop through builtin_attribute_functions to find the correct function
    for key in builtin_attribute_functions:
        if node.func.attr in builtin_attribute_functions[key]:
            nodeType = key;
            break;
    
    if nodeType == "": return None;

    
    result = builtin_attribute_functions[nodeType][node.func.attr];

    result = result + "(" + transpile_expression(node.func.value, block);

    if len(node.args) > 0:
        result = result + ", "
        # Loop through the args
        for i in range(0, len(node.args)):
                arg: ast.expr = node.args[i];
                result = result + transpile_expression(arg, block);

                if i != len(node.args) - 1:
                    result = result + ", ";

    result = result + ")";

    return result;

def transpile_call(node: ast.Call, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    if isinstance(node.func, ast.Attribute):
        p = process_builtin_attribute_function(node, block);
        if p is not None:
            result = result + p;
            return result;

    builtin: bool = (node.func.id in builtin_functions) or (node.func.id in builtin_functions["discriminate_tables"])

    # if not built-in:
    if not (isinstance(node.func, ast.Name) and not isinstance(node.func, ast.Attribute) and (builtin)):
        transpiled_func = transpile_expression(node.func, block)
        result = result + transpiled_func + "(";

        # Loop through the arguments
        for i in range(0, len(node.args)):
            arg = node.args[i];
            result = result + transpile_expression(arg, block);

            if i != len(node.args) - 1:
                result = result + ", ";
        
        result = result + ")";

        return result;
        
    func_name = node.func.id;

    if func_name == "help":
        # Reformulate help(function) to function([_,_,_,... (depending on #args) ],"help")
        func = node.args[0];
        # Get actual function from func (so we can get args length)
        func = get_function_block_by_name(func.id, block).node
        # Get amount of possible parameters
        num_args = len(func.args.args);

        result = result + func_name + "(" + ", ".join(["nil"]) * num_args + ",\"help\"";

        # Replace only first instance of "help" with func.name
        result = result.replace("help", func.name, 1);

        result = result + ")";
    elif func_name in builtin_functions["discriminate_tables"]:
        new_name = builtin_functions["discriminate_tables"][func_name];
        if len(node.args) == 0:
            result = result + new_name + ".list()";
        elif isinstance(node.args[0], ast.Dict):
            result = result + new_name + ".dict(" + transpile_expression(node.args[0], block) + ")";
        elif isinstance(node.args[0], ast.Set):
            result = result + new_name + ".set(" + transpile_expression(node.args[0], block) + ")";
        elif isinstance(node.args[0], ast.List):
            result = result + new_name + ".list(" + transpile_expression(node.args[0], block) + ")";
        elif isinstance(node.args[0], ast.Tuple):
            result = result + new_name + ".tuple(" + transpile_expression(node.args[0], block) + ")";
        elif isinstance(node.args[0], ast.GeneratorExp):
            result = result + new_name + ".tuple(" + transpile_expression(node.args[0], block) + ")";
        else:
            result = result + new_name + ".tuple(" + transpile_expression(node.args[0], block) + ")";
    else:
        result = result + builtin_functions[func_name];
        result = result + "(";
        # Loop through the arguments
        for i in range(0, len(node.args)):
        
        
            arg = node.args[i];
            result = result + transpile_expression(arg, block);

            if i != len(node.args) - 1:
                result = result + ", ";

        result = result + ")";        
            
    return result;

def transpile_while(node: ast.While, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "while " + transpile_expression(node.test, block) + " do\n";

    result = result + transpile_lines(node.body, block.add_child("while"));

    result = result + block.get_offset() + "end";

    return result;

def transpile_if(node: ast.If, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    if_line = "if " + transpile_expression(node.test, block);

    result = result + if_line;
    
    result = result + " then\n";

    result = result + transpile_lines(node.body, block.add_child("if"));

    if len(node.orelse) > 0:
        result = result + block.get_offset() + "else\n";

        result = result + transpile_lines(node.orelse, block.add_child("else"));

    result = result + block.get_offset() + "end\n";

    return result;

def transpile_function(node: ast.FunctionDef, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    # Get the function name
    function_name = node.name;

    result = "function " + function_name + "(";

    # Loop through the arguments
    for i in range(0, len(node.args.args)):
        arg = node.args.args[i];
        result = result + arg.arg;
        if i != len(node.args.args) - 1:
            result = result + ", ";

    result = result + ")";

    new_function_block = block.add_child("function", node);

    transpiled_body = transpile_lines(node.body, new_function_block);

    # Get first line of result
    first_line = transpiled_body.split("\n")[0];
    # Remove every character that resides between --[[ and ]] (ie remove comments)
    first_line = re.sub('--\[\[[^>]+\]]', '', first_line)
    # Remove every character that comes after -- (ie remove comments)
    first_line = re.sub('--.*', '', first_line)
    # Strip first line
    first_line = first_line.strip()

    # If this line is entirely surrounded by " or ', (i.e it is a string) then it's a help string
    if first_line.startswith('"') and first_line.endswith('"') or first_line.startswith("'") and first_line.endswith("'"):
        help_string = first_line;
        new_help_string = new_function_block.get_offset() + "if _ropy_help == \"help\" then return " + help_string + " end\n";
        # Remove the help_string from transpiled_body
        transpiled_body = transpiled_body.replace(help_string, "");

        # Add a parameter to the function (i.e replace the last ")" in result with ", _ropy_help)", in case there's =>1 args
        if len(node.args.args) > 0:
            result = result[:-1] + ", _ropy_help)";
        else:
            result = result + "_ropy_help)";
        
        result = result + "\n" + new_help_string

    header_length = len(result)
    result = result + "\n";

    result = result + transpiled_body

    has_yield = False;

    # Insert \nlocal variable declarations after header_length characters
    for variable in new_function_block.deep_variables:
        header = result[:header_length] + "\n"

        assigned_to = "nil";

        if variable == "yield":
            has_yield = True;
            assigned_to = "{}";
        
        result = header + new_function_block.get_offset() + "local " + variable + " = " + assigned_to + ";" + result[header_length:]

    # If has_yield, return yield
    if has_yield:
        result = result + new_function_block.get_offset() + "return yield\n";

    # Add end to the end of the function
    result = result + block.get_offset(-1) + "end\n";

    return result;

def transpile_boolop(node: ast.BoolOp, block: CodeBlock):
    result = initialise_string(node, block);

    # Loop through the values
    for i in range(0, len(node.values)):
        value = node.values[i];
        result = result + transpile_expression(value);
        if i != len(node.values) - 1:
            result = result + " " + transpile_expression(node.op);

    return result;

def transpile_return(node: ast.Return, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "return " + transpile_expression(node.value, block);

    return result;

def transpile_assign(node: ast.Assign, block: CodeBlock) -> str:

    result = initialise_string(node, block)

    # Check if assignment is new (i.e check if we have to append "local" in front of the variable)

    # Get targets as array
    targets = [];
    added: str = None # None | "surface" | "deep"

    for i in range(0, len(node.targets)):
        node_target = node.targets[i]
        target = transpile_expression(node_target, block)
        targets.append(target);
        
        if not isinstance(node_target, ast.Name): continue;
        added = block.add_variable(target)

    if added == "surface":
        result = result + "local ";

    # Assigns a variable to a value

    # Loop through the targets
    for i in range(0, len(targets)):
        target = targets[i];
        result = result + target
        if i != len(node.targets) - 1:
            result = result + ", ";

    result = result + " = ";

    result = result + transpile_expression(node.value, block);

    return result

def transpile_listcomp(node: ast.ListComp, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "(function()\n";

    result = result + block.get_offset(1) + "local result = {};\n";

    # Loop through the generators
    for i in range(0, len(node.generators)):
        generator = node.generators[i];
        target = transpile_expression(generator.target, block);
        iter = transpile_expression(generator.iter, block);
        ifs = generator.ifs;

        result = result + block.get_offset(1) + "for k, " + target
        result = result + " in pairs(" + iter + ") do\n";

        if len(ifs) == 0:
            result = result + block.get_offset(2) + "result[k] = " + transpile_expression(node.elt, block) + ";\n";
        else:
            for j in range(0, len(ifs)):
                if_ = ifs[j];
                result = result + block.get_offset(2) + "if " + transpile_expression(if_.test, block) + " then\n";
                result = result + block.get_offset(3)  + "result[k] = " + target + ";\n";
                result = result + block.get_offset(2) + "end\n";
            
        result = result + block.get_offset(2) + "end\n";

    result = result + block.get_offset(1) + "return result;\n";

    result = result + block.get_offset(-1) + "end)()";

    return result;

def transpile_generatorexp(node: ast.GeneratorExp, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "(function()\n";

    result = result + block.get_offset(1) + "local result = {};\n";

    # Loop through the generators
    for i in range(0, len(node.generators)):
        generator = node.generators[i];
        target = transpile_expression(generator.target, block);
        iter = transpile_expression(generator.iter, block);
        ifs = generator.ifs;

        result = result + block.get_offset(1) + "for k, " + target
        result = result + " in pairs(" + iter + ") do\n";

        if len(ifs) == 0:
            result = result + block.get_offset(2) + "result[k] = " + transpile_expression(node.elt, block) + ";\n";
        else:
            for j in range(0, len(ifs)):
                if_ = ifs[j];
                result = result + block.get_offset(2) + "if " + transpile_expression(if_.test, block) + " then\n";
                result = result + block.get_offset(3)  + "result[k] = " + target + ";\n";
                result = result + block.get_offset(2) + "end\n";

        result = result + block.get_offset(2) + "end\n";

    result = result + block.get_offset(1) + "return result;\n";

    result = result + block.get_offset() + "end)()";

    return result;


def transpile_for(node: ast.For, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "for _," + transpile_expression(node.target, block) + " in " + transpile_expression(node.iter, block) + " do\n";

    for_block = block.add_child("for")

    result = result + transpile_lines(node.body, for_block);

    result = result + for_block.get_offset(-1) + "end\n";

    return result;

def transpile_compare(node: ast.Compare, block: CodeBlock):
    result = initialise_string(node, block)

    # Loop through the expressions
    for i in range(0, len(node.ops)):
        op = node.ops[i];
        left = transpile_expression(node.left, block);
        comparator = transpile_expression(node.comparators[i], block);

        if isinstance(op, ast.Eq):
            result = result + left + " == " + comparator;
        elif isinstance(op, ast.NotEq):
            result = result + left + " ~= " + comparator;
        elif isinstance(op, ast.Lt):
            result = result + left + " < " + comparator;
        elif isinstance(op, ast.LtE):
            result = result + left + " <= " + comparator;
        elif isinstance(op, ast.Gt):
            result = result + left + " > " + comparator;
        elif isinstance(op, ast.GtE):
            result = result + left + " >= " + comparator;
        elif isinstance(op, ast.Is):
            result = result + left + " == " + comparator; # Probably wrong
        elif isinstance(op, ast.IsNot):
            result = result + left + " ~= " + comparator; # Probably wrong
        elif isinstance(op, ast.In):
            # ropy.operator_in(left, comparator)
            result = result + "ropy.operator_in(" + left + ", " + comparator + ")";
        elif isinstance(op, ast.NotIn):
            # not ropy.operator_in(left, comparator)
            result = result + "not ropy.operator_in(" + left + ", " + comparator + ")";

    return result;

def transpile_unaryop(node: ast.UnaryOp, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    # Check the operator
    if isinstance(node.op, ast.UAdd):
        result = result + "+";
    elif isinstance(node.op, ast.USub):
        result = result + "-";
    elif isinstance(node.op, ast.Not):
        result = result + "not ";
    elif isinstance(node.op, ast.Invert):
        result = result + "not ";

    result = result + transpile_expression(node.operand);

    return result;

def transpile_list(node: ast.List, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "{";

    # Loop through the expressions
    for i in range(0, len(node.elts)):
        elt = node.elts[i];
        result = result + transpile_expression(elt, block);
        if i != len(node.elts) - 1:
            result = result + ", ";

    result = result + "}";

    return result;

def transpile_lamba(node: ast.Lambda, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    # Header
    result = result + "function (";

    # Loop through the arguments
    for i in range(0, len(node.args.args)):
        arg = node.args.args[i];
        result = result + arg.arg;
        if i != len(node.args.args) - 1:
            result = result + ", ";

    result = result + ")";
    result = result + transpile_lines(node.body, block.add_child("lambda"));

    return result;

def transpile_binop(node: ast.BinOp, block: CodeBlock) -> str:
    # BinOp(expr left, operator op, expr right)
    result = initialise_string(node, block)
    
    result = result + transpile_expression(node.left, block);

    result = result + transpile_operator(node.op, block);

    result = result + transpile_expression(node.right, block);

    return result;

def transpile_yield(node: ast.Yield, block: CodeBlock):
    result = initialise_string(node, block)

    block.add_variable("yield");

    result = result + "yield[#yield+1] = " + transpile_expression(node.value, block);

    return result;

def transpile_subscript(node: ast.Subscript, block: CodeBlock):
    result = initialise_string(node, block)

    # Build the subscript in lua {} notation
    result = result + transpile_expression(node.value, block);
    result = result + "[";
    result = result + transpile_expression(node.slice, block);
    result = result + "]";

    return result;

def transpile_delete(node: ast.Delete, block: CodeBlock):
    result = initialise_string(node, block)

    # Loop through the targets and add " = nil" after it
    for i in range(0, len(node.targets)):
        target = node.targets[i];

        result = result + transpile_expression(target, block);

        if i != len(node.targets) - 1:
            result = result + ", ";

        result = result + " = nil";

    return result;

def transpile_augassign(node: ast.AugAssign, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    # x += 1
    # x = x + 1
    # target = target op value

    target = transpile_expression(node.target, block)
    op = transpile_operator(node.op, block)
    value = transpile_expression(node.value, block)

    result = target + " = " + target + " " + op + " " + value;

    return result;

def transpile_attribute(node: ast.Attribute, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + transpile_expression(node.value, block);
    result = result + "." + node.attr;

    return result;

def transpile_dict(node: ast.Dict, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "{";

    # Loop through the keys and values
    for i in range(0, len(node.keys)):
        key = node.keys[i];
        value = node.values[i];
        result = result + transpile_expression(key);
        result = result + " = ";
        result = result + transpile_expression(value);
        if i != len(node.keys) - 1:
            result = result + ", ";
    
    result = result + "}";

    return result;

def transpile_name(node: ast.Name, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + node.id;

    return result;

def transpile_string(node: ast.Str, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "\"" + node.s + "\"";

    return result;

def transpile_set(node: ast.Set, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "{";

    # Loop through the expressions
    for i in range(0, len(node.elts)):
        elt = node.elts[i];
        result = result + transpile_expression(elt, block);
        if i != len(node.elts) - 1:
            result = result + ", ";

    result = result + "}";

    return result;

def transpile_starred(node: ast.Starred, block: CodeBlock) -> str:
    result = initialise_string(node, block)

    result = result + "--[[*]]";
    result = result + transpile_expression(node.value, block);

    return result;

# Selector function
def transpile_expression(expression: ast.Expr | ast.expr, block: CodeBlock) -> str:
    # BoolOp
    if isinstance(expression, ast.BoolOp):
        return transpile_boolop(expression, block);

    # NamedExpr (probably needs to be a separate function)
    if isinstance(expression, ast.NamedExpr):
        return expression.name + " = " + transpile_expression(expression.value, block);

    # BinOp
    if isinstance(expression, ast.BinOp):
        return transpile_binop(expression, block);

    # UnaryOp
    if isinstance(expression, ast.UnaryOp):
        return transpile_unaryop(expression.op, block);
    
    # Lambda
    if isinstance(expression, ast.Lambda):
        return transpile_lamba(expression, block);

    # IfExp (should be a separate function)
    if isinstance(expression, ast.IfExp):
        return transpile_expression(expression.test, block) + " ? " + transpile_expression(expression.body, block) + " : " + transpile_expression(expression.orelse, block);

    # Dict (should be a separate function)
    if isinstance(expression, ast.Dict):
        return transpile_dict(expression, block);

    # Set (should be a separate function)
    if isinstance(expression, ast.Set):
        return transpile_set(expression, block);

    # Await (what is the equivalent in lua?)
    if isinstance(expression, ast.Await):
        return transpile_expression(expression.value, block);

    # Yield (what is the equivalent in lua?)
    if isinstance(expression, ast.Yield):
        return transpile_yield(expression, block);

    # Subscript
    if isinstance(expression, ast.Subscript):
        return transpile_subscript(expression, block);

    # Compare
    if isinstance(expression, ast.Compare):
        return transpile_compare(expression, block);

    # List
    if isinstance(expression, ast.List):
        return transpile_list(expression, block);

    # ListComp
    if isinstance(expression, ast.ListComp):
        return transpile_listcomp(expression, block);

    # GeneratorExpr
    if isinstance(expression, ast.GeneratorExp):
        return transpile_generatorexp(expression, block);

    # Attribute
    if isinstance(expression, ast.Attribute):
        return transpile_attribute(expression, block);
    
    # Call
    if isinstance(expression, ast.Call):
        return transpile_call(expression, block);

    # Name
    if isinstance(expression, ast.Name):
        return transpile_name(expression, block);

    # Num (should be a separate function)
    if isinstance(expression, ast.Num):
        return str(expression.n);

    # Str
    if isinstance(expression, ast.Str):
        return transpile_string(expression, block);

    # Expr
    if isinstance(expression, ast.Expr):
        return transpile_expression(expression.value, block);

    # Starred
    if isinstance(expression, ast.Starred):
        return transpile_starred(expression, block);

    print("Warning: unknown expression " + expression.__class__.__name__);
    exit();

# Selector function
def transpile_statement(statement: ast.stmt | list[ast.stmt], block: CodeBlock) -> str:
    # If the statement is a FunctionDef
    if isinstance(statement, ast.FunctionDef):
        return transpile_function(statement, block);

    # If the statement is a If
    if isinstance(statement, ast.If):
        return transpile_if(statement, block);

    # Return
    if isinstance(statement, ast.Return):
        return transpile_return(statement, block);

    # Delete
    if isinstance(statement, ast.Delete):
        return transpile_delete(statement, block);

    # While
    if isinstance(statement, ast.While):
        return transpile_while(statement, block);

    # Assign
    if isinstance(statement, ast.Assign):
        return transpile_assign(statement, block);

    # AugAssign
    if isinstance(statement, ast.AugAssign):
        return transpile_augassign(statement, block);

    # For
    if isinstance(statement, ast.For):
        return transpile_for(statement, block);

    # Expr
    if isinstance(statement, ast.Expr):
        return transpile_expression(statement.value, block);

    print("Warning: unknown statement " + statement.__class__.__name__)
    exit();

# Selector function
def transpile_operator(operator: ast.operator, block: CodeBlock) -> str:
    result = initialise_string(operator, block)

    # Check the operator
    if isinstance(operator, ast.Add):
        return result + "+";

    if isinstance(operator, ast.Sub):
        return result + "-";

    if isinstance(operator, ast.Mult):
        return result + "*";

    if isinstance(operator, ast.Div):
        return result + "/";

    if isinstance(operator, ast.Mod):
        return result + "%";

    if isinstance(operator, ast.Pow):
        return result + "^";
    
    print("Warning: Unknown operator " + operator.__class__.__name__);
    exit();

def transpile_statements(statements: list[ast.stmt], block: CodeBlock) -> str:
    result = "";

    for statement in statements:
        result = result + transpile_statement(statement, block);

    return result;

def transpile_expressions(expressions: list[ast.expr], block: CodeBlock) -> str:
    result = "";

    for expression in expressions:
        result = result + transpile_expression(expression, block);

    return result;

# Selector function
def transpile_line(node: ast.Expr | ast.expr | ast.stmt, block: CodeBlock) -> str:
    # Check if statement or expression
    result = "";

    if isinstance(node, ast.Expr) or isinstance(node, ast.expr):
        result = transpile_expression(node, block);

    if isinstance(node, ast.stmt):
        result = transpile_statement(node, block);

    if isinstance(node, ast.operator):
        result = transpile_operator(node, block);

    if result == "":
        print("Warning: unknown node " + node.__class__.__name__ + " which inherits from " + node.__class__.__bases__[0].__name__);
        exit();
    
    return (
        block.get_offset() + result + 
        ( (" -- Line " + str(node.lineno) + "\n") if toggle_line_of_code else "\n" )
    );

def transpile_lines(node: list[ast.expr | ast.Expr | ast.stmt | ast.operator], block: CodeBlock) -> str:
    # If statement is a list of statements/expressions
    result: str = "";

    if node.__class__.__name__ != "list":
        return result;

    for i in range(0, len(node)):
        result = result + transpile_line(node[i], block);

    return result;

def transpile_module(module: ast.Module) -> str:
    global top_block
    result = 'local ropy = require(game:FindFirstChild("ropy", true))\n\n';
    result = result + transpile_lines(module.body, top_block);

    # Reset top block
    top_block = CodeBlock("0", "module", [], []);

    return result