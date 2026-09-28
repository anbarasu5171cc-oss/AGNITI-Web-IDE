import re
from abc import ABC, abstractmethod


class CodeGenerator:
    def __init__(self, ast):
        self.ast = ast
        self.code = []
        self.indent_level = 0

    def add_line(self, line):
        indent = "    " * self.indent_level
        self.code.append(indent + line)

    def convert_value(self, value):
        value = value.strip()

        if value.lower() == "true":
            return "True"

        if value.lower() == "false":
            return "False"

        if value.startswith('"') and value.endswith('"'):
            return value

        if re.fullmatch(r"-?\d+", value):
            return value

        if re.fullmatch(r"-?\d+\.\d+", value):
            return value

        return value

    def convert_operand(self, value):
        value = value.strip()

        if re.fullmatch(r'"[A-Za-z_][A-Za-z0-9_]*"', value):
            return value[1:-1]

        return self.convert_value(value)

    def convert_dictionary_value(self, value):
        value = value.strip()
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            return value
        return self.convert_operand(value)

    def convert_expression(self, expression):
        expression = expression.strip()

        # Boolean values
        expression = re.sub(
            r'\btrue\b',
            'True',
            expression,
            flags=re.IGNORECASE
        )

        expression = re.sub(
            r'\bfalse\b',
            'False',
            expression,
            flags=re.IGNORECASE
        )

        # Logical operators
        expression = re.sub(
            r'\bAND\b',
            'and',
            expression,
            flags=re.IGNORECASE
        )

        expression = re.sub(
            r'\bOR\b',
            'or',
            expression,
            flags=re.IGNORECASE
        )

        expression = re.sub(
            r'\bNOT\b',
            'not',
            expression,
            flags=re.IGNORECASE
        )

        # Quoted variable names
        expression = re.sub(
            r'"([A-Za-z_][A-Za-z0-9_]*)"',
            r'\1',
            expression
        )

        return expression

    def generate(self):
        original_statements = self.ast["statements"]
        function_statements = [
            statement
            for statement in original_statements
            if statement.get("type") == "Function"
        ]

        if function_statements:
            statements = (
                [
                    statement
                    for statement in original_statements
                    if statement.get("type") == "Start"
                ]
                + function_statements
                + [
                    statement
                    for statement in original_statements
                    if statement.get("type") not in ("Start", "Function", "End")
                ]
                + [
                    statement
                    for statement in original_statements
                    if statement.get("type") == "End"
                ]
            )
        else:
            statements = original_statements

        for statement in statements:
            statement_type = statement["type"]

            # START
            if statement_type == "Start":
                self.add_line("# AGNITI Program")
                if any(
                    statement.get("type") == "Class" and statement.get("abstract")
                    for statement in original_statements
                ):
                    self.add_line("from abc import ABC, abstractmethod")
                if any(statement.get("type") == "RandomInteger" for statement in original_statements):
                    self.add_line("import random")
                if any(statement.get("type") in ("JsonEncode", "JsonDecode") for statement in original_statements):
                    self.add_line("import json")
                if any(statement.get("type") in ("RuntimeStart", "RuntimeStop", "RuntimeDisplay") for statement in original_statements):
                    self.add_line("import time")
                self.add_line("")

            # END
            elif statement_type == "End":
                continue

            # Runtime measurement
            elif statement_type == "RuntimeStart":
                self.add_line("_agn_runtime_start = time.perf_counter()")

            elif statement_type == "RuntimeStop":
                result = statement["result"]
                self.add_line(f"{result} = time.perf_counter() - _agn_runtime_start")
                self.add_line(f"_agn_runtime_elapsed = {result}")

            elif statement_type == "RuntimeDisplay":
                self.add_line("print(_agn_runtime_elapsed)")

            # Display text
            elif statement_type == "Display":
                value = statement["value"]
                self.add_line(f"print({value})")

            # Display variable
            elif statement_type == "DisplayVariable":
                variable = statement["variable"]
                self.add_line(f"print({variable})")

            # Generic typed input
            elif statement_type == "Input":
                variable = statement["variable"]
                data_type = statement["data_type"]
                if data_type == "integer":
                    self.add_line(f'{variable} = int(input("Enter {variable}: "))')
                elif data_type == "decimal":
                    self.add_line(f'{variable} = float(input("Enter {variable}: "))')
                elif data_type == "boolean":
                    self.add_line(f'{variable} = input("Enter {variable} (true/false): ").strip().lower() == "true"')
                else:
                    self.add_line(f'{variable} = input("Enter {variable}: ")')

            # Integer input
            elif statement_type == "InputInteger":
                variable = statement["variable"]
                self.add_line(
                    f'{variable} = int(input("Enter {variable}: "))'
                )

            # String input
            elif statement_type == "InputString":
                variable = statement["variable"]
                self.add_line(
                    f'{variable} = input("Enter {variable}: ")'
                )

            # Decimal input
            elif statement_type == "InputDecimal":
                variable = statement["variable"]
                self.add_line(
                    f'{variable} = float(input("Enter {variable}: "))'
                )

            # Boolean input
            elif statement_type == "InputBoolean":
                variable = statement["variable"]
                self.add_line(
                    f'{variable} = input("Enter {variable} (true/false): ").strip().lower() == "true"'
                )

            # Basic type conversion
            elif statement_type == "Convert":
                value = self.convert_operand(statement["value"])
                target_type = statement["target_type"]
                result = statement["result"]
                conversion = {
                    "integer": "int",
                    "decimal": "float",
                    "string": "str",
                    "boolean": "bool"
                }[target_type]
                self.add_line(f"{result} = {conversion}({value})")

            # Basic math operations
            elif statement_type == "MathOperation":
                operation = statement["operation"]
                result = statement["result"]
                if operation == "abs":
                    self.add_line(f"{result} = abs({self.convert_operand(statement['value'])})")
                elif operation == "min":
                    left = self.convert_operand(statement["left"])
                    right = self.convert_operand(statement["right"])
                    self.add_line(f"{result} = min({left}, {right})")
                elif operation == "max":
                    left = self.convert_operand(statement["left"])
                    right = self.convert_operand(statement["right"])
                    self.add_line(f"{result} = max({left}, {right})")
                elif operation == "round":
                    value = self.convert_operand(statement["value"])
                    self.add_line(f"{result} = round({value}, {statement['digits']})")

            # Random integer
            elif statement_type == "RandomInteger":
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                self.add_line(f"{statement['result']} = random.randint({left}, {right})")

            # Current date
            elif statement_type == "CurrentDate":
                self.add_line("from datetime import date")
                self.add_line(f"{statement['result']} = date.today().isoformat()")

            # Current time
            elif statement_type == "CurrentTime":
                self.add_line("from datetime import datetime")
                self.add_line(f"{statement['result']} = datetime.now().strftime('%H:%M:%S')")

            # JSON encode
            elif statement_type == "JsonEncode":
                self.add_line(f"{statement['result']} = json.dumps({statement['variable']})")

            # JSON decode
            elif statement_type == "JsonDecode":
                self.add_line(f"{statement['result']} = json.loads({statement['variable']})")

            # Basic assertion
            elif statement_type == "Assert":
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                self.add_line(f"assert {left} == {right}")

            # Direct assignment
            elif statement_type == "Assignment":
                variable = statement["variable"]
                value = statement["value"]

                converted_value = self.convert_value(value)

                self.add_line(
                    f"{variable} = {converted_value}"
                )

            # List creation
            elif statement_type == "List":
                variable = statement["variable"]
                values = statement["values"]

                if isinstance(values, str):
                    values = [
                        value.strip()
                        for value in values.split(",")
                        if value.strip()
                    ]

                converted_values = [
                    self.convert_value(value)
                    for value in values
                ]

                self.add_line(
                    f"{variable} = [{', '.join(converted_values)}]"
                )

            # List item access
            elif statement_type == "ListItemAccess":
                list_variable = statement["list"]
                index = self.convert_operand(statement["index"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {list_variable}[{index}]"
                )

            # List length
            elif statement_type == "ListLength":
                list_variable = statement["list"]
                result = statement["result"]

                self.add_line(
                    f"{result} = len({list_variable})"
                )

            # List append
            elif statement_type == "ListAppend":
                list_variable = statement["list"]
                value = self.convert_value(statement["value"])

                self.add_line(
                    f"{list_variable}.append({value})"
                )

            # List insert
            elif statement_type == "ListInsert":
                list_variable = statement["list"]
                index = self.convert_operand(statement["index"])
                value = self.convert_value(statement["value"])

                self.add_line(
                    f"{list_variable}.insert({index}, {value})"
                )

            # List remove
            elif statement_type == "ListRemove":
                list_variable = statement["list"]
                value = self.convert_value(statement["value"])

                self.add_line(
                    f"{list_variable}.remove({value})"
                )

            # List pop
            elif statement_type == "ListPop":
                list_variable = statement["list"]
                result = statement["result"]

                self.add_line(
                    f"{result} = {list_variable}.pop()"
                )

            # List clear
            elif statement_type == "ListClear":
                list_variable = statement["list"]

                self.add_line(
                    f"{list_variable}.clear()"
                )

            # List index of
            elif statement_type == "ListIndexOf":
                list_variable = statement["list"]
                value = self.convert_value(statement["value"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {list_variable}.index({value})"
                )

            # List contains
            elif statement_type == "ListContains":
                list_variable = statement["list"]
                value = self.convert_value(statement["value"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {value} in {list_variable}"
                )

            # List find / search
            elif statement_type == "ListFind":
                list_variable = statement["list"]
                value = self.convert_value(statement["value"])
                result = statement["result"]

                self.add_line(
                    f"{result} = next((item for item in {list_variable} if item == {value}), None)"
                )

            # List range
            elif statement_type == "ListRange":
                start = self.convert_operand(statement["start"])
                end = self.convert_operand(statement["end"])
                result = statement["result"]

                self.add_line(
                    f"{result} = list(range({start}, {end} + 1))"
                )

            # List unique / remove duplicates
            elif statement_type == "ListUnique":
                list_variable = statement["list"]
                result = statement["result"]

                self.add_line(
                    f"{result} = list(dict.fromkeys({list_variable}))"
                )

            # List filter
            elif statement_type == "ListFilter":
                list_variable = statement["list"]
                operator = statement["operator"]
                value = self.convert_value(statement["value"])
                result = statement["result"]

                self.add_line(
                    f"{result} = [item for item in {list_variable} if item {operator} {value}]"
                )

            # List map / transform
            elif statement_type == "ListMap":
                list_variable = statement["list"]
                operation = statement["operation"]
                value = self.convert_value(statement["value"])
                result = statement["result"]

                self.add_line(
                    f"{result} = [item {operation} {value} for item in {list_variable}]"
                )

            # List any
            elif statement_type == "ListAny":
                list_variable = statement["list"]
                result = statement["result"]

                self.add_line(
                    f"{result} = any({list_variable})"
                )

            # List all
            elif statement_type == "ListAll":
                list_variable = statement["list"]
                result = statement["result"]

                self.add_line(
                    f"{result} = all({list_variable})"
                )

            # List reverse
            elif statement_type == "ListReverse":
                list_variable = statement["list"]

                self.add_line(
                    f"{list_variable}.reverse()"
                )

            # List sort
            elif statement_type == "ListSort":
                list_variable = statement["list"]

                self.add_line(
                    f"{list_variable}.sort()"
                )

            # List copy
            elif statement_type == "ListCopy":
                list_variable = statement["list"]
                result = statement["result"]

                self.add_line(
                    f"{result} = {list_variable}.copy()"
                )

            # List extend
            elif statement_type == "ListExtend":
                list_variable = statement["list"]
                source_variable = statement["source"]

                self.add_line(
                    f"{list_variable}.extend({source_variable})"
                )

            # List slice
            elif statement_type == "ListSlice":
                list_variable = statement["list"]
                start = self.convert_operand(statement["start"])
                end = self.convert_operand(statement["end"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {list_variable}[{start}:{end}]"
                )

            # List join
            elif statement_type == "ListJoin":
                list_variable = statement["list"]
                separator = self.convert_value(statement["separator"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {separator}.join({list_variable})"
                )

            # List split
            elif statement_type == "ListSplit":
                text = self.convert_value(statement["text"])
                separator = self.convert_value(statement["separator"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {text}.split({separator})"
                )

            # List min
            elif statement_type == "ListMin":
                list_variable = statement["list"]
                result = statement["result"]

                self.add_line(
                    f"{result} = min({list_variable})"
                )

            # List empty
            elif statement_type == "ListEmpty":
                list_variable = statement["list"]
                result = statement["result"]

                self.add_line(
                    f"{result} = len({list_variable}) == 0"
                )

            # List item update
            elif statement_type == "ListItemUpdate":
                list_variable = statement["list"]
                index = self.convert_operand(statement["index"])
                value = self.convert_value(statement["value"])

                self.add_line(
                    f"{list_variable}[{index}] = {value}"
                )

            # Increase
            elif statement_type == "Increase":
                variable = statement["variable"]

                amount = statement.get(
                    "amount",
                    statement.get("value", "1")
                )

                self.add_line(
                    f"{variable} += {self.convert_operand(amount)}"
                )

            # Decrease
            elif statement_type == "Decrease":
                variable = statement["variable"]

                amount = statement.get(
                    "amount",
                    statement.get("value", "1")
                )

                self.add_line(
                    f"{variable} -= {self.convert_operand(amount)}"
                )

            # Addition
            elif statement_type in ("Addition", "Add"):
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {left} + {right}"
                )

            # Subtraction
            elif statement_type in ("Subtraction", "Subtract"):
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {left} - {right}"
                )

            # Multiplication
            elif statement_type in ("Multiplication", "Multiply"):
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {left} * {right}"
                )

            # Division
            elif statement_type in ("Division", "Divide"):
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {left} / {right}"
                )

            # Advanced expression
            elif statement_type == "Expression":
                expression = statement["expression"]
                result = statement["result"]

                agniti_expression = self.convert_expression(
                    expression
                )

                self.add_line(
                    f"{result} = {agniti_expression}"
                )

            # String concatenation
            elif statement_type == "StringConcatenation":
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                result = statement["result"]

                self.add_line(
                    f"{result} = str({left}) + str({right})"
                )

            # String length
            elif statement_type == "StringLength":
                variable = statement["variable"]
                result = statement["result"]

                self.add_line(
                    f"{result} = len({variable})"
                )

            # String uppercase
            elif statement_type in ("StringUpper", "StringUppercase"):
                variable = statement["variable"]
                result = statement["result"]

                self.add_line(
                    f"{result} = {variable}.upper()"
                )

            # String lowercase
            elif statement_type in ("StringLower", "StringLowercase"):
                variable = statement["variable"]
                result = statement["result"]

                self.add_line(
                    f"{result} = {variable}.lower()"
                )

            # String replace
            elif statement_type == "StringReplace":
                variable = statement["variable"]
                old_value = statement["old"]
                new_value = statement["new"]
                result = statement["result"]

                self.add_line(
                    f"{result} = {variable}.replace({old_value}, {new_value})"
                )

            # String contains
            elif statement_type == "StringContains":
                result = statement["result"]

                if "value" in statement:
                    variable = statement["variable"]
                    value = statement["value"]

                else:
                    variable = statement["variable"]
                    value = statement["search"]

                value = self.convert_operand(value)

                self.add_line(
                    f"{result} = {value} in {variable}"
                )

            # String starts with / ends with
            elif statement_type == "StringStartsWith":
                self.add_line(f"{statement['result']} = {statement['variable']}.startswith({repr(statement['prefix'])})")
            elif statement_type == "StringEndsWith":
                self.add_line(f"{statement['result']} = {statement['variable']}.endswith({repr(statement['suffix'])})")
            elif statement_type == "StringFind":
                self.add_line(f"{statement['result']} = {statement['variable']}.find({repr(statement['search'])})")
            elif statement_type == "StringIndex":
                self.add_line(f"{statement['result']} = {statement['variable']}.index({repr(statement['search'])})")
            elif statement_type == "StringCount":
                self.add_line(f"{statement['result']} = {statement['variable']}.count({repr(statement['search'])})")
            elif statement_type == "StringTrim":
                self.add_line(f"{statement['result']} = {statement['variable']}.strip()")
            elif statement_type == "StringLeftTrim":
                self.add_line(f"{statement['result']} = {statement['variable']}.lstrip()")
            elif statement_type == "StringRightTrim":
                self.add_line(f"{statement['result']} = {statement['variable']}.rstrip()")
            elif statement_type == "StringSplit":
                self.add_line(f"{statement['result']} = {statement['variable']}.split({repr(statement['separator'])})")
            elif statement_type == "StringJoin":
                self.add_line(f"{statement['result']} = {repr(statement['separator'])}.join({statement['list']})")
            elif statement_type == "StringSubstring":
                self.add_line(f"{statement['result']} = {statement['variable']}[{self.convert_operand(statement['start'])}:{self.convert_operand(statement['end'])}]")
            elif statement_type == "StringCharacter":
                self.add_line(f"{statement['result']} = {statement['variable']}[{self.convert_operand(statement['index'])}]")
            elif statement_type == "StringReverse":
                self.add_line(f"{statement['result']} = {statement['variable']}[::-1]")
            elif statement_type == "StringRepeat":
                self.add_line(f"{statement['result']} = {statement['variable']} * {self.convert_operand(statement['count'])}")
            elif statement_type == "StringCapitalize":
                self.add_line(f"{statement['result']} = {statement['variable']}.capitalize()")
            elif statement_type == "StringTitle":
                self.add_line(f"{statement['result']} = {statement['variable']}.title()")
            elif statement_type == "StringSwapCase":
                self.add_line(f"{statement['result']} = {statement['variable']}.swapcase()")
            elif statement_type == "StringValidation":
                method = {'alphabetic':'isalpha','numeric':'isdigit','alphanumeric':'isalnum','lowercase':'islower','uppercase':'isupper'}.get(statement['validation'], statement['validation'])
                self.add_line(f"{statement['result']} = {statement['variable']}.{method}()")
            elif statement_type == "StringFormat":
                self.add_line(f"{statement['result']} = {statement['template']}.format(name={statement['variable']})")
            elif statement_type == "StringInterpolate":
                self.add_line(f"{statement['result']} = {statement['template']}.replace('{{name}}', str({statement['variable']}))")

            # File operations
            elif statement_type == "FileRead":
                self.add_line(f"with open({statement['file']!r}, 'r', encoding='utf-8') as _f: {statement['result']} = _f.read()")
            elif statement_type == "FileWrite":
                self.add_line(f"with open({statement['file']!r}, 'w', encoding='utf-8') as _f: _f.write(str({self.convert_dictionary_value(statement['value'])}))")
            elif statement_type == "FileAppend":
                self.add_line(f"with open({statement['file']!r}, 'a', encoding='utf-8') as _f: _f.write(str({self.convert_dictionary_value(statement['value'])}))")
            elif statement_type == "FileExists":
                self.add_line(f"import os")
                self.add_line(f"{statement['result']} = os.path.exists({statement['file']!r})")
            elif statement_type == "FileDelete":
                self.add_line(f"import os")
                self.add_line(f"os.remove({statement['file']!r}) if os.path.exists({statement['file']!r}) else None")
            elif statement_type == "FileSize":
                self.add_line(f"import os")
                self.add_line(f"{statement['result']} = os.path.getsize({statement['file']!r})")
            elif statement_type == "FileRename":
                self.add_line(f"import os")
                self.add_line(f"os.rename({statement['source']!r}, {statement['destination']!r})")
            elif statement_type == "FileCopy":
                self.add_line(f"import shutil")
                self.add_line(f"shutil.copy({statement['source']!r}, {statement['destination']!r})")
            elif statement_type == "FileMove":
                self.add_line(f"import shutil")
                self.add_line(f"shutil.move({statement['source']!r}, {statement['destination']!r})")
            elif statement_type == "DirectoryList":
                self.add_line(f"import os")
                self.add_line(f"{statement['result']} = os.listdir({statement['directory']!r})")

            # List enumerate / zip
            elif statement_type == "ListEnumerate":
                self.add_line(f"{statement['result']} = list(enumerate({statement['list']}))")
            elif statement_type == "ListZip":
                self.add_line(f"{statement['result']} = list(zip({statement['first']}, {statement['second']}))")

            # Boolean AND
            elif statement_type == "BooleanAnd":
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {left} and {right}"
                )

            # Boolean OR
            elif statement_type == "BooleanOr":
                left = self.convert_operand(statement["left"])
                right = self.convert_operand(statement["right"])
                result = statement["result"]

                self.add_line(
                    f"{result} = {left} or {right}"
                )

            # Boolean NOT
            elif statement_type == "BooleanNot":
                variable = self.convert_operand(
                    statement["variable"]
                )

                result = statement["result"]

                self.add_line(
                    f"{result} = not {variable}"
                )

            # BOOLEAN OPERATION
            elif statement_type == "BooleanOperation":
                operation = statement["operation"]
                result = statement["result"]

                if operation == "and":
                    left = self.convert_operand(
                        statement["left"]
                    )
                    right = self.convert_operand(
                        statement["right"]
                    )

                    self.add_line(
                        f"{result} = {left} and {right}"
                    )

                elif operation == "or":
                    left = self.convert_operand(
                        statement["left"]
                    )
                    right = self.convert_operand(
                        statement["right"]
                    )

                    self.add_line(
                        f"{result} = {left} or {right}"
                    )

                elif operation == "not":
                    left = self.convert_operand(
                        statement["left"]
                    )

                    self.add_line(
                        f"{result} = not {left}"
                    )

            # IF
            elif statement_type == "If":
                if "condition" in statement:
                    condition = self.convert_expression(
                        statement["condition"]
                    )

                else:
                    variable = statement["variable"]
                    operator = statement["operator"]
                    value = self.convert_operand(
                        statement["value"]
                    )

                    operator_map = {
                        "greater than": ">",
                        "less than": "<",
                        "greater than or equal to": ">=",
                        "less than or equal to": "<=",
                        "equal to": "==",
                        "not equal to": "!="
                    }

                    condition = (
                        f"{variable} "
                        f"{operator_map.get(operator, operator)} "
                        f"{value}"
                    )

                self.add_line(
                    f"if {condition}:"
                )

                self.indent_level += 1

            # NOT IF
            elif statement_type == "NotIf":
                condition = self.convert_expression(
                    statement["condition"]
                )

                self.add_line(
                    f"if not ({condition}):"
                )

                self.indent_level += 1

            # LOGICAL IF
            elif statement_type == "LogicalIf":
                condition = self.convert_expression(
                    statement["condition"]
                )

                self.add_line(
                    f"if {condition}:"
                )

                self.indent_level += 1

            # OTHERWISE IF
            elif statement_type == "ElseIf":
                self.indent_level -= 1

                if "condition" in statement:
                    condition = self.convert_expression(
                        statement["condition"]
                    )

                else:
                    variable = statement["variable"]
                    operator = statement["operator"]
                    value = self.convert_operand(
                        statement["value"]
                    )

                    operator_map = {
                        "greater than": ">",
                        "less than": "<",
                        "greater than or equal to": ">=",
                        "less than or equal to": "<=",
                        "equal to": "==",
                        "not equal to": "!="
                    }

                    condition = (
                        f"{variable} "
                        f"{operator_map.get(operator, operator)} "
                        f"{value}"
                    )

                self.add_line(
                    f"elif {condition}:"
                )

                self.indent_level += 1

            # OTHERWISE
            elif statement_type == "Else":
                self.indent_level -= 1

                self.add_line("else:")

                self.indent_level += 1

            # END IF
            elif statement_type == "EndIf":
                self.indent_level -= 1

            # REPEAT
            elif statement_type == "Repeat":
                count = self.convert_operand(
                    statement["count"]
                )

                self.add_line(
                    f"for _ in range({count}):"
                )

                self.indent_level += 1

            # END REPEAT
            elif statement_type == "EndRepeat":
                self.indent_level -= 1

            # FOR EACH
            elif statement_type == "ForEach":
                variable = statement.get(
                    "variable",
                    statement.get("item")
                )

                collection = statement["collection"]

                self.add_line(
                    f"for {variable} in {collection}:"
                )

                self.indent_level += 1

            # END FOR EACH
            elif statement_type == "EndForEach":
                self.indent_level -= 1

            # WHILE
            elif statement_type == "While":
                if "condition" in statement:
                    condition = self.convert_expression(
                        statement["condition"]
                    )

                else:
                    variable = statement["variable"]
                    operator = statement["operator"]
                    value = self.convert_operand(
                        statement["value"]
                    )

                    operator_map = {
                        "greater than": ">",
                        "less than": "<",
                        "greater than or equal to": ">=",
                        "less than or equal to": "<=",
                        "equal to": "==",
                        "not equal to": "!="
                    }

                    condition = (
                        f"{variable} "
                        f"{operator_map.get(operator, operator)} "
                        f"{value}"
                    )

                self.add_line(
                    f"while {condition}:"
                )

                self.indent_level += 1

            # END WHILE
            elif statement_type == "EndWhile":
                self.indent_level -= 1

            # BREAK
            elif statement_type == "Break":
                self.add_line("break")

            # CONTINUE
            elif statement_type == "Continue":
                self.add_line("continue")

            # FUNCTION
            elif statement_type == "Function":
                name = statement["name"]

                # NEW: optional parameters
                parameters = statement.get("parameters", [])
                defaults = statement.get("defaults", {})

                parameter_parts = []
                for parameter in parameters:
                    if parameter in defaults:
                        default_value = self.convert_value(
                            defaults[parameter]
                        )
                        parameter_parts.append(
                            f"{parameter}={default_value}"
                        )
                    else:
                        parameter_parts.append(parameter)

                params = ", ".join(parameter_parts)

                self.add_line(
                    f"def {name}({params}):"
                )

                self.indent_level += 1

                body = statement.get("body", [])

                if body:
                    temp_generator = CodeGenerator({
                        "type": "Program",
                        "statements": body
                    })

                    generated_body = temp_generator.generate()

                    if generated_body:
                        for generated_line in generated_body.splitlines():
                            self.add_line(generated_line)

                else:
                    self.add_line("pass")

                self.indent_level -= 1

                self.add_line("")

            # OBJECT CREATION
            elif statement_type == "ObjectCreation":
                class_name = statement["class"]
                object_name = statement["object"]
                arguments = [self.convert_value(argument) for argument in statement.get("args", [])]
                args_text = ", ".join(arguments)
                self.add_line(f"{object_name} = {class_name}({args_text})")

            # OBJECT PROPERTY UPDATE
            elif statement_type == "ObjectPropertyUpdate":
                object_name = statement["object"]
                property_name = statement["property"]
                value = self.convert_value(statement["value"])
                self.add_line(f"{object_name}.{property_name} = {value}")

            # OBJECT PROPERTY ACCESS
            elif statement_type == "ObjectPropertyAccess":
                object_name = statement["object"]
                property_name = statement["property"]
                result = statement["result"]
                self.add_line(f"{result} = {object_name}.{property_name}")

            # OBJECT PROPERTY DISPLAY
            elif statement_type == "ObjectPropertyDisplay":
                object_name = statement["object"]
                property_name = statement["property"]
                self.add_line(f"print({object_name}.{property_name})")

            # CLASS VARIABLE ACCESS
            elif statement_type == "ClassVariableAccess":
                call = f"{statement['class']}.{statement['name']}"
                self.add_line(f"{statement['result']} = {call}")

            # CLASS VARIABLE DISPLAY
            elif statement_type == "ClassVariableDisplay":
                self.add_line(f"print({statement['class']}.{statement['name']})")

            # OBJECT EQUALITY
            elif statement_type == "ObjectEquality":
                self.add_line(f"{statement['result']} = {statement['left']} == {statement['right']}")

            # STATIC METHOD CALL
            elif statement_type == "StaticMethodCall":
                arguments = ", ".join(self.convert_value(a) for a in statement.get("args", []))
                call = f"{statement['class']}.{statement['method']}({arguments})"
                if statement.get("result"):
                    self.add_line(f"{statement['result']} = {call}")
                else:
                    self.add_line(call)

            # METHOD CALL
            elif statement_type == "MethodCall":
                object_name = statement["object"]
                method_name = statement["method"]
                arguments = [self.convert_value(argument) for argument in statement.get("args", [])]
                args_text = ", ".join(arguments)
                call = f"{object_name}.{method_name}({args_text})"
                if statement.get("result"):
                    self.add_line(f"{statement['result']} = {call}")
                else:
                    self.add_line(call)

            # CLASS DEFINITION
            elif statement_type == "Class":
                name = statement["name"]
                parents = statement.get("parents", [])
                if not parents and statement.get("parent"):
                    parents = [statement.get("parent")]
                if statement.get("abstract") and "ABC" not in parents:
                    parents = parents + ["ABC"]
                if statement.get("interface") and "ABC" not in parents:
                    parents = parents + ["ABC"]
                if statement.get("interfaces"):
                    parents = parents + [p for p in statement["interfaces"] if p not in parents]
                parent_text = ", ".join(parents)
                class_header = f"class {name}" + (f"({parent_text})" if parent_text else "") + ":"
                self.add_line(class_header)
                self.indent_level += 1

                body = statement.get("body", [])
                if body:
                    method_groups = {}
                    for member in body:
                        if member.get("type") == "Method":
                            method_groups.setdefault(member.get("name"), []).append(member)
                    consumed = set()
                    for member_index, member in enumerate(body):
                        if member_index in consumed:
                            continue
                        if member.get("type") == "Method" and len(method_groups.get(member.get("name"), [])) > 1:
                            overloads = method_groups[member.get("name")]
                            for idx, overload in enumerate(overloads, 1):
                                params = overload.get("parameters", [])
                                defaults = overload.get("defaults", {})
                                parts = [f"{p}={self.convert_value(defaults[p])}" if p in defaults else p for p in params]
                                param_text = ", ".join(parts)
                                self.add_line(f"def _agn_{member.get('name')}_{idx}(self{', ' if param_text else ''}{param_text}):")
                                self.indent_level += 1
                                body_code = CodeGenerator({"type":"Program","statements":overload.get("body", [])}).generate()
                                if body_code:
                                    for line in body_code.splitlines(): self.add_line(line)
                                else:
                                    self.add_line("pass")
                                self.indent_level -= 1
                            self.add_line(f"def {member.get('name')}(self, *args):")
                            self.indent_level += 1
                            for idx, overload in enumerate(overloads, 1):
                                count = len(overload.get("parameters", []))
                                self.add_line(f"if len(args) == {count}:") if idx == 1 else self.add_line(f"elif len(args) == {count}:")
                                self.indent_level += 1
                                self.add_line(f"return self._agn_{member.get('name')}_{idx}(*args)")
                                self.indent_level -= 1
                            self.add_line(f"raise TypeError(\"No overload of {member.get('name')} accepts this number of arguments.\")")
                            self.indent_level -= 1
                            for m in overloads:
                                consumed.add(body.index(m))
                            continue
                        temp_generator = CodeGenerator({"type": "Program", "statements": [member]})
                        generated_member = temp_generator.generate()
                        if generated_member:
                            for line in generated_member.splitlines(): self.add_line(line)
                else:
                    self.add_line("pass")

                self.indent_level -= 1
                self.add_line("")

            # CONSTRUCTOR
            elif statement_type == "Constructor":
                parameters = statement.get("parameters", [])
                defaults = statement.get("defaults", {})
                parameter_parts = []
                for parameter in parameters:
                    if parameter in defaults:
                        parameter_parts.append(
                            f"{parameter}={self.convert_value(defaults[parameter])}"
                        )
                    else:
                        parameter_parts.append(parameter)
                params = ", ".join(parameter_parts)
                self.add_line(f"def __init__(self{', ' if params else ''}{params}):")
                self.indent_level += 1

                body = statement.get("body", [])
                if body:
                    temp_generator = CodeGenerator({
                        "type": "Program",
                        "statements": body
                    })
                    generated_body = temp_generator.generate()
                    if generated_body:
                        for generated_line in generated_body.splitlines():
                            self.add_line(generated_line)
                else:
                    self.add_line("pass")

                self.indent_level -= 1

            # CLASS VARIABLE
            elif statement_type == "ClassVariableSet":
                name = statement["name"]
                value = self.convert_value(statement["value"])
                self.add_line(f"{name} = {value}")

            # ABSTRACT METHOD
            elif statement_type == "AbstractMethod":
                name = statement["name"]
                parameters = statement.get("parameters", [])
                defaults = statement.get("defaults", {})
                parameter_parts = []
                for parameter in parameters:
                    if parameter in defaults:
                        parameter_parts.append(f"{parameter}={self.convert_value(defaults[parameter])}")
                    else:
                        parameter_parts.append(parameter)
                params = ", ".join(parameter_parts)
                self.add_line("@abstractmethod")
                self.add_line(f"def {name}(self{', ' if params else ''}{params}):")
                self.indent_level += 1
                self.add_line("pass")
                self.indent_level -= 1

            # STATIC METHOD
            elif statement_type == "StaticMethod":
                name = statement["name"]
                parameters = statement.get("parameters", [])
                defaults = statement.get("defaults", {})
                parameter_parts = []
                for parameter in parameters:
                    if parameter in defaults:
                        parameter_parts.append(f"{parameter}={self.convert_value(defaults[parameter])}")
                    else:
                        parameter_parts.append(parameter)
                params = ", ".join(parameter_parts)
                self.add_line("@staticmethod")
                self.add_line(f"def {name}({params}):")
                self.indent_level += 1
                body = statement.get("body", [])
                if body:
                    temp_generator = CodeGenerator({"type":"Program","statements":body})
                    generated_body = temp_generator.generate()
                    if generated_body:
                        for generated_line in generated_body.splitlines(): self.add_line(generated_line)
                else:
                    self.add_line("pass")
                self.indent_level -= 1

            # PARENT METHOD CALL
            elif statement_type == "ParentMethodCall":
                arguments = ", ".join(self.convert_value(a) for a in statement.get("args", []))
                self.add_line(f"super().{statement['method']}({arguments})")

            # PRIVATE PROPERTY DISPLAY
            elif statement_type == "PrivatePropertyDisplay":
                self.add_line(f"print(self._{statement['property']})")

            # PRIVATE PROPERTY SET
            elif statement_type == "PrivatePropertySet":
                self.add_line(f"self._{statement['property']} = {self.convert_value(statement['value'])}")

            # GETTER
            elif statement_type == "Getter":
                prop = statement["property"]
                self.add_line("@property")
                self.add_line(f"def {prop}(self):")
                self.indent_level += 1
                self.add_line(f"return self._{prop}")
                self.indent_level -= 1

            # SETTER
            elif statement_type == "Setter":
                prop = statement["property"]
                self.add_line(f"@{prop}.setter")
                self.add_line(f"def {prop}(self, value):")
                self.indent_level += 1
                self.add_line(f"self._{prop} = value")
                self.indent_level -= 1

            # OPERATOR OVERLOAD
            elif statement_type == "OperatorMethod":
                op = statement["operator"]
                magic = {"+":"__add__","-":"__sub__","*":"__mul__","/":"__truediv__","%":"__mod__","==":"__eq__","!=":"__ne__","<":"__lt__",">":"__gt__","<=":"__le__",">=":"__ge__"}[op]
                param = statement.get("parameter")
                params = f", {param}" if param else ""
                self.add_line(f"def {magic}(self{params}):")
                self.indent_level += 1
                body = statement.get("body", [])
                if body:
                    temp_generator = CodeGenerator({"type":"Program","statements":body})
                    generated_body = temp_generator.generate()
                    if generated_body:
                        for line in generated_body.splitlines(): self.add_line(line)
                else:
                    self.add_line("pass")
                self.indent_level -= 1

            # METHOD
            elif statement_type == "Method":
                name = statement["name"]
                parameters = statement.get("parameters", [])
                defaults = statement.get("defaults", {})
                parameter_parts = []
                for parameter in parameters:
                    if parameter in defaults:
                        parameter_parts.append(
                            f"{parameter}={self.convert_value(defaults[parameter])}"
                        )
                    else:
                        parameter_parts.append(parameter)
                params = ", ".join(parameter_parts)
                self.add_line(f"def {name}(self{', ' if params else ''}{params}):")
                self.indent_level += 1

                body = statement.get("body", [])
                if body:
                    temp_generator = CodeGenerator({
                        "type": "Program",
                        "statements": body
                    })
                    generated_body = temp_generator.generate()
                    if generated_body:
                        for generated_line in generated_body.splitlines():
                            self.add_line(generated_line)
                else:
                    self.add_line("pass")

                self.indent_level -= 1

            # PROPERTY SET
            elif statement_type == "PropertySet":
                property_name = statement["property"]
                value = self.convert_value(statement["value"])
                self.add_line(f"self.{property_name} = {value}")

            # PROPERTY DISPLAY
            elif statement_type == "PropertyDisplay":
                property_name = statement["property"]
                self.add_line(f"print(self.{property_name})")

            # FUNCTION DEF - EXISTING FORMAT
            elif statement_type == "FunctionDef":
                name = statement["name"]

                params = ", ".join(
                    statement.get(
                        "params",
                        statement.get("parameters", [])
                    )
                )

                self.add_line(
                    f"def {name}({params}):"
                )

                self.indent_level += 1

            # END FUNCTION
            elif statement_type == "EndFunction":
                self.indent_level -= 1

            # RETURN
            elif statement_type == "Return":
                # Current parser format:
                # {"type": "Return", "variable": "result"}
                #
                # Older Return format:
                # {"type": "Return", "value": ...}
                #
                # Preserve both formats.
                if "variable" in statement:
                    value = statement["variable"]

                else:
                    value = self.convert_operand(
                        statement["value"]
                    )

                self.add_line(
                    f"return {value}"
                )

            # FUNCTION CALL
            elif statement_type == "FunctionCall":
                name = statement["name"]

                args = statement.get("args", [])

                converted_args = []

                for arg in args:
                    arg = arg.strip()

                    # Preserve quoted string arguments.
                    # Example:
                    # "Anbarasu" -> "Anbarasu"
                    #
                    # Existing convert_operand() behavior is preserved
                    # for all other argument types.
                    if (
                        len(arg) >= 2
                        and arg.startswith('"')
                        and arg.endswith('"')
                    ):
                        converted_args.append(arg)

                    else:
                        converted_args.append(
                            self.convert_operand(arg)
                        )

                converted_args = ", ".join(
                    converted_args
                )

                # Result is optional for basic function calls.
                result = statement.get("result")

                if result:
                    self.add_line(
                        f"{result} = {name}({converted_args})"
                    )

                else:
                    self.add_line(
                        f"{name}({converted_args})"
                    )

            # DICTIONARY CREATE
            elif statement_type == "Dictionary":
                variable = statement["variable"]

                self.add_line(
                    f"{variable} = {{}}"
                )

            # DICTIONARY SET
            elif statement_type == "DictionarySet":
                key = statement["key"]

                value = self.convert_dictionary_value(
                    statement["value"]
                )

                dictionary = statement["dictionary"]

                self.add_line(
                    f"{dictionary}['{key}'] = {value}"
                )

            # DICTIONARY GET
            elif statement_type == "DictionaryGet":
                key = statement["key"]
                dictionary = statement["dictionary"]
                result = statement["result"]

                self.add_line(
                    f"{result} = {dictionary}['{key}']"
                )

            # DICTIONARY CLEAR
            elif statement_type == "DictionaryClear":
                self.add_line(f"{statement['dictionary']}.clear()")

            # DICTIONARY UPDATE
            elif statement_type == "DictionaryUpdate":
                value = self.convert_dictionary_value(statement["value"])
                self.add_line(f"{statement['dictionary']}['{statement['key']}'] = {value}")

            # DICTIONARY REMOVE
            elif statement_type == "DictionaryRemove":
                self.add_line(f"del {statement['dictionary']}['{statement['key']}']")

            # DICTIONARY CONTAINS
            elif statement_type == "DictionaryContains":
                self.add_line(f"{statement['result']} = '{statement['key']}' in {statement['dictionary']}")

            # DICTIONARY LENGTH
            elif statement_type == "DictionaryLength":
                self.add_line(f"{statement['result']} = len({statement['dictionary']})")

            # DICTIONARY ITEMS / VALUES / KEYS
            elif statement_type == "DictionaryItems":
                self.add_line(f"{statement['result']} = list({statement['dictionary']}.items())")
            elif statement_type == "DictionaryValues":
                self.add_line(f"{statement['result']} = list({statement['dictionary']}.values())")
            elif statement_type == "DictionaryKeys":
                self.add_line(f"{statement['result']} = list({statement['dictionary']}.keys())")

            # DICTIONARY COPY
            elif statement_type == "DictionaryCopy":
                self.add_line(f"{statement['result']} = {statement['dictionary']}.copy()")

            # DICTIONARY MERGE
            elif statement_type == "DictionaryMerge":
                self.add_line(f"{statement['target']}.update({statement['source']})")
            elif statement_type == "DictionaryMergeNew":
                self.add_line(f"{statement['result']} = {{**{statement['first']}, **{statement['second']}}}")

            # DICTIONARY POP
            elif statement_type == "DictionaryPop":
                self.add_line(f"{statement['result']} = {statement['dictionary']}.pop('{statement['key']}')")
            elif statement_type == "DictionaryPopDefault":
                default = self.convert_dictionary_value(statement['default'])
                self.add_line(f"{statement['result']} = {statement['dictionary']}.pop('{statement['key']}', {default})")

            # DICTIONARY GET DEFAULT
            elif statement_type == "DictionaryGetDefault":
                default = self.convert_dictionary_value(statement['default'])
                self.add_line(f"{statement['result']} = {statement['dictionary']}.get('{statement['key']}', {default})")

            # DICTIONARY SET DEFAULT
            elif statement_type == "DictionarySetDefault":
                value = self.convert_dictionary_value(statement['value'])
                self.add_line(f"{statement['dictionary']}.setdefault('{statement['key']}', {value})")

            # DICTIONARY VALUE EXISTS
            elif statement_type == "DictionaryValueContains":
                value = self.convert_dictionary_value(statement['value'])
                self.add_line(f"{statement['result']} = {value} in {statement['dictionary']}.values()")

            # DICTIONARY FILTER
            elif statement_type == "DictionaryFilter":
                value = self.convert_dictionary_value(statement['value'])
                op = statement['operator']
                self.add_line(f"{statement['result']} = {{k: v for k, v in {statement['dictionary']}.items() if v {op} {value}}}")

            # DICTIONARY MAP
            elif statement_type == "DictionaryMap":
                value = self.convert_dictionary_value(statement['value'])
                op = statement['operation']
                self.add_line(f"{statement['result']} = {{k: v {op} {value} for k, v in {statement['dictionary']}.items()}}")

            # DICTIONARY INVERT
            elif statement_type == "DictionaryInvert":
                self.add_line(f"{statement['result']} = {{v: k for k, v in {statement['dictionary']}.items()}}")

            # DICTIONARY SORT
            elif statement_type == "DictionarySort":
                if statement['by'] == 'key':
                    self.add_line(f"{statement['result']} = dict(sorted({statement['dictionary']}.items(), key=lambda item: item[0]))")
                else:
                    self.add_line(f"{statement['result']} = dict(sorted({statement['dictionary']}.items(), key=lambda item: item[1]))")

            # DICTIONARY FROM LISTS
            elif statement_type == "DictionaryFromLists":
                self.add_line(f"{statement['result']} = dict(zip({statement['keys']}, {statement['values']}))")

            # DICTIONARY FROM PAIRS
            elif statement_type == "DictionaryFromPairs":
                self.add_line(f"{statement['result']} = dict({statement['pairs']})")

        return "\n".join(self.code)


if __name__ == "__main__":
    pass
