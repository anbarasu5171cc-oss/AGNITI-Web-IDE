import re


class Parser:
    def __init__(self, tokens, known_variables=None, inside_function=False):
        self.tokens = tokens
        self.position = 0
        self.known_variables = known_variables or []
        self.inside_function = inside_function
        self.function_signatures = self.collect_function_signatures()

    def parse_parameter_declarations(self, parameter_text):
        declarations = re.findall(
            r'"([^"]*)"(?:\s+of\s+(integer|string|decimal|boolean)\s+type)?'
            r'(?:\s+defaulting\s+to\s+("[^"]*"|-?\d+(?:\.\d+)?|true|false))?',
            parameter_text,
            re.IGNORECASE
        )

        parameters = []
        parameter_types = {}
        defaults = {}

        for parameter, data_type, default_value in declarations:
            parameters.append(parameter)

            if data_type:
                parameter_types[parameter] = data_type.lower()

            if default_value:
                defaults[parameter] = default_value.strip()

        return parameters, parameter_types, defaults

    def collect_function_signatures(self):
        signatures = {}

        for token in self.tokens:
            if token[0] != "STEP":
                continue

            instruction = re.sub(r'^Step\s+\d+:\s*', '', token[2].strip(), flags=re.IGNORECASE)

            function_match = re.search(
                r'Define a function named\s+"([^"]+)"\s+with parameter(?:s)?\s+(.+)',
                instruction,
                re.IGNORECASE
            )

            if function_match:
                function_name = function_match.group(1)
                parameter_text = function_match.group(2).strip()

                return_type = None
                return_type_match = re.search(
                    r'\s+and\s+return type\s+(integer|string|decimal|boolean)\s*$',
                    parameter_text,
                    re.IGNORECASE
                )
                if return_type_match:
                    return_type = return_type_match.group(1).lower()
                    parameter_text = parameter_text[:return_type_match.start()].strip()

                parameter_values, parameter_types, defaults = self.parse_parameter_declarations(
                    parameter_text
                )

                signature = {
                    "type": "Function",
                    "name": function_name,
                    "parameters": parameter_values
                }

                if defaults:
                    signature["defaults"] = defaults

                if parameter_types:
                    signature["parameter_types"] = parameter_types

                if return_type:
                    signature["return_type"] = return_type

                signatures[function_name] = signature

            else:
                function_match = re.search(
                    r'Define a function named\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                )

                if function_match:
                    function_name = function_match.group(1)
                    signature = {
                        "type": "Function",
                        "name": function_name,
                        "parameters": []
                    }

                    return_type_match = re.search(
                        r'with return type\s+(integer|string|decimal|boolean)\s*$',
                        instruction,
                        re.IGNORECASE
                    )
                    if return_type_match:
                        signature["return_type"] = return_type_match.group(1).lower()

                    signatures[function_name] = signature

        return signatures

    def get_function_statement(self, program, function_name):
        function_statement = next(
            (statement for statement in program["statements"]
             if statement.get("type") == "Function"
             and statement.get("name") == function_name),
            None
        )

        if function_statement is not None:
            return function_statement

        return self.function_signatures.get(function_name)

    def infer_argument_type(self, argument):
        argument = argument.strip()

        if re.fullmatch(r'-?\d+', argument):
            return "integer"
        if re.fullmatch(r'-?\d+\.\d+', argument):
            return "decimal"
        if len(argument) >= 2 and argument.startswith('"') and argument.endswith('"'):
            return "string"
        if argument.lower() in ("true", "false"):
            return "boolean"
        return None

    def validate_argument_types(self, function_name, function_statement, arguments):
        parameter_types = function_statement.get("parameter_types", {})
        parameters = function_statement.get("parameters", [])

        for index, argument in enumerate(arguments):
            if index >= len(parameters):
                break
            parameter = parameters[index]
            expected_type = parameter_types.get(parameter)
            if not expected_type:
                continue
            actual_type = self.infer_argument_type(argument)
            if actual_type is not None and actual_type != expected_type:
                raise SyntaxError(
                    f'Function "{function_name}" parameter "{parameter}" expects '
                    f'{expected_type} but got {actual_type}.'
                )

    def infer_return_variable_type(self, variable, body, parameter_types):
        variable = variable.strip()
        if (
            len(variable) >= 2
            and variable.startswith('"')
            and variable.endswith('"')
        ):
            variable = variable[1:-1]

        inferred_types = dict(parameter_types)

        def resolve_type(value):
            value = value.strip()
            direct_type = self.infer_argument_type(value)
            if direct_type:
                return direct_type
            if (
                len(value) >= 2
                and value.startswith('"')
                and value.endswith('"')
            ):
                value = value[1:-1]
            return inferred_types.get(value)

        for statement in body:
            statement_type = statement.get("type")
            result = statement.get("result")

            if statement_type in (
                "InputInteger",
                "InputString",
                "InputDecimal",
                "InputBoolean"
            ):
                inferred_types[statement.get("variable")] = {
                    "InputInteger": "integer",
                    "InputString": "string",
                    "InputDecimal": "decimal",
                    "InputBoolean": "boolean"
                }[statement_type]
                continue

            if statement_type == "Assignment" and result is None:
                value_type = self.infer_argument_type(statement.get("value", ""))
                if value_type:
                    inferred_types[statement.get("variable")] = value_type
                else:
                    resolved_type = resolve_type(statement.get("value", ""))
                    if resolved_type:
                        inferred_types[statement.get("variable")] = resolved_type
                continue

            if result:
                if statement_type in ("Add", "Subtract", "Multiply", "Modulus"):
                    left_type = resolve_type(statement.get("left", ""))
                    right_type = resolve_type(statement.get("right", ""))
                    if left_type == "decimal" or right_type == "decimal":
                        inferred_types[result] = "decimal"
                    elif left_type == "integer" and right_type == "integer":
                        inferred_types[result] = "integer"

                elif statement_type == "Divide":
                    left_type = resolve_type(statement.get("left", ""))
                    right_type = resolve_type(statement.get("right", ""))
                    if left_type and right_type:
                        inferred_types[result] = "decimal"

                elif statement_type in (
                    "StringConcatenation",
                    "StringReplace",
                    "StringUppercase",
                    "StringLowercase",
                    "StringStartsWith",
                    "StringEndsWith",
                    "StringTrim",
                    "StringLeftTrim",
                    "StringRightTrim",
                    "StringCapitalize",
                    "StringTitle",
                    "StringSwapCase",
                    "StringReverse",
                    "StringRepeat",
                    "StringSubstring",
                    "StringCharacter",
                    "StringSplit",
                    "StringJoin",
                    "StringFormat",
                    "StringInterpolate",
                    "FileRead"
                ):
                    inferred_types[result] = "string"

                elif statement_type in (
                    "StringLength",
                    "StringFind",
                    "StringIndex",
                    "StringCount",
                    "StringLength",
                    "ListLength",
                ):
                    inferred_types[result] = "integer"

                elif statement_type == "ListJoin":
                    inferred_types[result] = "string"

                elif statement_type in (
                    "StringSplit",
                    "ListSplit",
                    "ListFilter",
                    "ListMap",
                    "ListUnique",
                    "ListZip",
                    "ListEnumerate"
                ):
                    inferred_types[result] = "list"

                elif statement_type in (
                    "StringContains",
                    "StringStartsWith",
                    "StringEndsWith",
                    "StringValidation",
                    "FileExists",
                    "ListContains",
                    "ListEmpty",
                    "ListAny",
                    "ListAll",
                    "DictionaryContains",
                    "DictionaryValueContains",
                    "BooleanOperation"
                ):
                    inferred_types[result] = "boolean"

                elif statement_type in (
                    "DictionaryCopy",
                    "DictionaryMergeNew",
                    "DictionaryFilter",
                    "DictionaryMap",
                    "DictionaryInvert",
                    "DictionarySort",
                    "DictionaryFromLists",
                    "DictionaryFromPairs"
                ):
                    inferred_types[result] = "dictionary"

                elif statement_type in (
                    "DictionaryKeys",
                    "DictionaryValues",
                    "DictionaryItems"
                ):
                    inferred_types[result] = "list"

                elif statement_type in (
                    "DictionaryLength",
                ):
                    inferred_types[result] = "integer"

                elif statement_type == "FunctionCall":
                    called_function = self.function_signatures.get(statement.get("name"))
                    if called_function and called_function.get("return_type"):
                        inferred_types[result] = called_function["return_type"]

        return inferred_types.get(variable)

    def validate_return_type(self, function_name, return_type, body, parameter_types):
        if not return_type:
            return

        has_return = False

        for statement in body:
            if statement.get("type") != "Return":
                continue

            has_return = True

            variable = statement.get("variable")
            actual_type = self.infer_return_variable_type(
                variable,
                body,
                parameter_types
            )

            if actual_type is not None and actual_type != return_type:
                raise SyntaxError(
                    f'Function "{function_name}" expects return type {return_type} but got {actual_type}.'
                )

        if not has_return:
            raise SyntaxError(
                f'Function "{function_name}" must return a value of type {return_type}.'
            )

    def parse_class_body(self, body_tokens, class_name):
        body_statements = []
        position = 0

        while position < len(body_tokens):
            token = body_tokens[position]
            if token[0] != "STEP":
                position += 1
                continue

            instruction = re.sub(
                r'^Step\s+\d+:\s*',
                '',
                token[2].strip(),
                flags=re.IGNORECASE
            )

            # Constructor
            constructor_match = re.search(
                r'Define a constructor(?: for class\s+"([^"]+)")?\s+with parameter(?:s)?\s+(.+)',
                instruction,
                re.IGNORECASE
            )
            constructor_no_params = re.fullmatch(
                r'Define a constructor(?: for class\s+"([^"]+)")?',
                instruction,
                re.IGNORECASE
            )

            if constructor_match or constructor_no_params:
                declared_class = (
                    constructor_match.group(1)
                    if constructor_match else constructor_no_params.group(1)
                )
                if declared_class and declared_class != class_name:
                    raise SyntaxError(
                        f'Constructor belongs to class "{declared_class}" but is inside class "{class_name}".'
                    )

                parameter_text = constructor_match.group(2) if constructor_match else ""
                parameters, parameter_types, defaults = self.parse_parameter_declarations(
                    parameter_text
                ) if parameter_text else ([], {}, {})

                end_position = None
                for search_position in range(position + 1, len(body_tokens)):
                    search_token = body_tokens[search_position]
                    if search_token[0] != "STEP":
                        continue
                    search_instruction = re.sub(
                        r'^Step\s+\d+:\s*',
                        '',
                        search_token[2].strip(),
                        flags=re.IGNORECASE
                    )
                    if re.search(r'End the constructor', search_instruction, re.IGNORECASE):
                        end_position = search_position
                        break

                if end_position is None:
                    raise SyntaxError(
                        f'Constructor for class "{class_name}" is missing "End the constructor".'
                    )

                for parameter in parameters:
                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', parameter):
                        raise SyntaxError(
                            f'Invalid constructor parameter name: "{parameter}".'
                        )

                inner_tokens = body_tokens[position + 1:end_position]
                constructor_body = self.parse_class_member_body(inner_tokens, parameters)

                constructor_statement = {
                    "type": "Constructor",
                    "parameters": parameters,
                    "body": constructor_body
                }
                if parameter_types:
                    constructor_statement["parameter_types"] = parameter_types
                if defaults:
                    constructor_statement["defaults"] = defaults

                body_statements.append(constructor_statement)
                position = end_position + 1
                continue

            # Class variable
            class_variable_match = re.fullmatch(
                r'Set the class variable "([^"]+)" to (.+)',
                instruction,
                re.IGNORECASE
            )
            if class_variable_match:
                body_statements.append({
                    "type": "ClassVariableSet",
                    "name": class_variable_match.group(1),
                    "value": class_variable_match.group(2).strip()
                })
                position += 1
                continue

            # Abstract method
            abstract_method_match = re.fullmatch(
                r'Define an abstract method named "([^"]+)"(?: with parameter(?:s)? (.+))?',
                instruction,
                re.IGNORECASE
            )
            if abstract_method_match:
                method_name = abstract_method_match.group(1)
                parameter_text = abstract_method_match.group(2) or ""
                parameters, parameter_types, defaults = self.parse_parameter_declarations(parameter_text) if parameter_text else ([], {}, {})
                end_position = None
                for search_position in range(position + 1, len(body_tokens)):
                    search_token = body_tokens[search_position]
                    if search_token[0] != "STEP":
                        continue
                    search_instruction = re.sub(r'^Step\s+\d+:\s*', '', search_token[2].strip(), flags=re.IGNORECASE)
                    if re.search(r'End the method', search_instruction, re.IGNORECASE):
                        end_position = search_position
                        break
                if end_position is None:
                    raise SyntaxError(f'Abstract method "{method_name}" is missing "End the method".')
                method_statement = {
                    "type": "AbstractMethod",
                    "name": method_name,
                    "parameters": parameters,
                    "body": []
                }
                if parameter_types:
                    method_statement["parameter_types"] = parameter_types
                if defaults:
                    method_statement["defaults"] = defaults
                body_statements.append(method_statement)
                position = end_position + 1
                continue

            # Static method
            static_method_match = re.search(
                r'Define a static method named\s+"([^"]+)"(?:\s+with parameter(?:s)?\s+(.+))?',
                instruction,
                re.IGNORECASE
            )
            if static_method_match:
                method_name = static_method_match.group(1)
                parameter_text = static_method_match.group(2) or ""
                parameters, parameter_types, defaults = self.parse_parameter_declarations(parameter_text) if parameter_text else ([], {}, {})
                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', method_name):
                    raise SyntaxError(f'Invalid static method name: "{method_name}".')
                end_position = None
                for search_position in range(position + 1, len(body_tokens)):
                    search_token = body_tokens[search_position]
                    if search_token[0] != "STEP":
                        continue
                    search_instruction = re.sub(r'^Step\s+\d+:\s*', '', search_token[2].strip(), flags=re.IGNORECASE)
                    if re.search(r'End the method', search_instruction, re.IGNORECASE):
                        end_position = search_position
                        break
                if end_position is None:
                    raise SyntaxError(f'Static method "{method_name}" is missing "End the method".')
                method_body = self.parse_class_member_body(body_tokens[position + 1:end_position], parameters)
                method_statement = {"type":"StaticMethod","name":method_name,"parameters":parameters,"body":method_body}
                if parameter_types: method_statement["parameter_types"] = parameter_types
                if defaults: method_statement["defaults"] = defaults
                body_statements.append(method_statement)
                position = end_position + 1
                continue

            # Method with parameters
            method_match = re.search(
                r'Define a method named\s+"([^"]+)"\s+with parameter(?:s)?\s+(.+)',
                instruction,
                re.IGNORECASE
            )
            method_no_params = re.fullmatch(
                r'Define a method named\s+"([^"]+)"',
                instruction,
                re.IGNORECASE
            )

            if method_match or method_no_params:
                method_name = method_match.group(1) if method_match else method_no_params.group(1)
                parameter_text = method_match.group(2) if method_match else ""
                parameters, parameter_types, defaults = self.parse_parameter_declarations(
                    parameter_text
                ) if parameter_text else ([], {}, {})

                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', method_name):
                    raise SyntaxError(f'Invalid method name: "{method_name}".')

                end_position = None
                for search_position in range(position + 1, len(body_tokens)):
                    search_token = body_tokens[search_position]
                    if search_token[0] != "STEP":
                        continue
                    search_instruction = re.sub(
                        r'^Step\s+\d+:\s*',
                        '',
                        search_token[2].strip(),
                        flags=re.IGNORECASE
                    )
                    if re.search(r'End the method', search_instruction, re.IGNORECASE):
                        end_position = search_position
                        break

                if end_position is None:
                    raise SyntaxError(
                        f'Method "{method_name}" is missing "End the method".'
                    )

                inner_tokens = body_tokens[position + 1:end_position]
                method_body = self.parse_class_member_body(inner_tokens, parameters)
                method_statement = {
                    "type": "Method",
                    "name": method_name,
                    "parameters": parameters,
                    "body": method_body
                }
                if parameter_types:
                    method_statement["parameter_types"] = parameter_types
                if defaults:
                    method_statement["defaults"] = defaults

                body_statements.append(method_statement)
                position = end_position + 1
                continue

            # Getter
            getter_match = re.fullmatch(
                r'Define a getter for property "([^"]+)"',
                instruction, re.IGNORECASE
            )
            if getter_match:
                body_statements.append({"type": "Getter", "property": getter_match.group(1)})
                position += 1
                continue

            # Setter
            setter_match = re.fullmatch(
                r'Define a setter for property "([^"]+)"',
                instruction, re.IGNORECASE
            )
            if setter_match:
                body_statements.append({"type": "Setter", "property": setter_match.group(1)})
                position += 1
                continue

            # Operator overload
            operator_match = re.fullmatch(
                r'Define an operator method "([+\-*/%]|==|!=|<|>|<=|>=)"(?: with parameter "([^"]+)")?',
                instruction, re.IGNORECASE
            )
            if operator_match:
                operator = operator_match.group(1)
                parameter = operator_match.group(2)
                end_position = None
                for search_position in range(position + 1, len(body_tokens)):
                    search_token = body_tokens[search_position]
                    if search_token[0] != "STEP":
                        continue
                    search_instruction = re.sub(r'^Step\s+\d+:\s*', '', search_token[2].strip(), flags=re.IGNORECASE)
                    if re.search(r'End the operator method', search_instruction, re.IGNORECASE):
                        end_position = search_position
                        break
                if end_position is None:
                    raise SyntaxError(f'Operator method "{operator}" is missing "End the operator method".')
                parameters = [parameter] if parameter else []
                method_body = self.parse_class_member_body(body_tokens[position + 1:end_position], parameters)
                body_statements.append({"type":"OperatorMethod","operator":operator,"parameter":parameter,"body":method_body})
                position = end_position + 1
                continue

            # Private property assignment
            private_property_match = re.search(
                r'Set the private property "([^"]+)" to (.+)',
                instruction,
                re.IGNORECASE
            )
            if private_property_match:
                property_name = private_property_match.group(1)
                value_text = private_property_match.group(2).strip()
                parameter_match = re.fullmatch(
                    r'the value of parameter "([^"]+)"',
                    value_text,
                    re.IGNORECASE
                )
                if parameter_match:
                    value = parameter_match.group(1)
                else:
                    value = value_text
                body_statements.append({
                    "type": "PrivatePropertySet",
                    "property": property_name,
                    "value": value
                })
                position += 1
                continue

            # Constructor/method property assignment
            property_match = re.search(
                r'Set the property\s+"([^"]+)"\s+to\s+(.+)',
                instruction,
                re.IGNORECASE
            )
            if property_match:
                property_name = property_match.group(1)
                value_text = property_match.group(2).strip()
                parameter_match = re.fullmatch(
                    r'the value of parameter\s+"([^"]+)"',
                    value_text,
                    re.IGNORECASE
                )
                if parameter_match:
                    value = parameter_match.group(1)
                    if value not in getattr(self, "known_variables", []):
                        raise SyntaxError(
                            f'Unknown constructor or method parameter "{value}".'
                        )
                    value_kind = "parameter"
                else:
                    value = value_text
                    value_kind = "expression"

                body_statements.append({
                    "type": "PropertySet",
                    "property": property_name,
                    "value": value,
                    "value_kind": value_kind
                })
                position += 1
                continue

            # Display a property of the current object (self)
            property_display = re.fullmatch(
                r'Display the property\s+"([^"]+)"',
                instruction,
                re.IGNORECASE
            )
            if property_display:
                body_statements.append({
                    "type": "PropertyDisplay",
                    "property": property_display.group(1)
                })
                position += 1
                continue

            # For all existing AGNITI statements, reuse the normal parser.
            try:
                parsed = Parser(
                    [token],
                    known_variables=getattr(self, "known_variables", []),
                    inside_function=True
                ).parse()
                body_statements.extend(parsed.get("statements", []))
            except Exception:
                raise

            position += 1

        return body_statements

    def parse_class_member_body(self, body_tokens, parameters):
        body_statements = []
        position = 0

        while position < len(body_tokens):
            token = body_tokens[position]
            if token[0] != "STEP":
                position += 1
                continue

            instruction = re.sub(
                r'^Step\s+\d+:\s*',
                '',
                token[2].strip(),
                flags=re.IGNORECASE
            )

            # Parent method call
            parent_method = re.fullmatch(
                r'Call the parent method "([^"]+)"(?: with (.*))?',
                instruction,
                re.IGNORECASE
            )
            if parent_method:
                arguments = []
                if parent_method.group(2):
                    arguments = re.findall(
                        r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*',
                        parent_method.group(2)
                    )
                    arguments = [a for a in arguments if a.lower() != "and"]
                body_statements.append({
                    "type": "ParentMethodCall",
                    "method": parent_method.group(1),
                    "args": arguments
                })
                position += 1
                continue

            # Private property display inside class methods
            private_display = re.fullmatch(
                r'Display the private property "([^"]+)"',
                instruction,
                re.IGNORECASE
            )
            if private_display:
                body_statements.append({
                    "type": "PrivatePropertyDisplay",
                    "property": private_display.group(1)
                })
                position += 1
                continue

            # Private property assignment
            private_property_match = re.fullmatch(
                r'Set the private property "([^"]+)" to (.+)',
                instruction,
                re.IGNORECASE
            )
            if private_property_match:
                property_name = private_property_match.group(1)
                value_text = private_property_match.group(2).strip()
                parameter_match = re.fullmatch(
                    r'the value of parameter "([^"]+)"',
                    value_text,
                    re.IGNORECASE
                )
                if parameter_match:
                    value = parameter_match.group(1)
                    if value not in parameters:
                        raise SyntaxError(f'Unknown constructor or method parameter "{value}".')
                else:
                    value = value_text
                body_statements.append({
                    "type": "PrivatePropertySet",
                    "property": property_name,
                    "value": value
                })
                position += 1
                continue

            property_match = re.fullmatch(
                r'Set the property\s+"([^"]+)"\s+to\s+(.+)',
                instruction,
                re.IGNORECASE
            )
            if property_match:
                property_name = property_match.group(1)
                value_text = property_match.group(2).strip()
                parameter_match = re.fullmatch(
                    r'the value of parameter\s+"([^"]+)"',
                    value_text,
                    re.IGNORECASE
                )
                if parameter_match:
                    value = parameter_match.group(1)
                    if value not in parameters:
                        raise SyntaxError(
                            f'Unknown constructor or method parameter "{value}".'
                        )
                    value_kind = "parameter"
                else:
                    value = value_text
                    value_kind = "expression"

                body_statements.append({
                    "type": "PropertySet",
                    "property": property_name,
                    "value": value,
                    "value_kind": value_kind
                })
                position += 1
                continue

            property_display = re.fullmatch(
                r'Display the property\s+"([^"]+)"',
                instruction,
                re.IGNORECASE
            )
            if property_display:
                body_statements.append({
                    "type": "PropertyDisplay",
                    "property": property_display.group(1)
                })
                position += 1
                continue

            # Return an expression from a class method/operator method
            return_expression = re.fullmatch(
                r'Return the expression\s+"(.+)"',
                instruction,
                re.IGNORECASE
            )
            if return_expression:
                body_statements.append({"type": "Return", "value": return_expression.group(1)})
                position += 1
                continue

            # Existing statements can use parameters as known variables.
            parsed = Parser(
                [token],
                known_variables=parameters,
                inside_function=True
            ).parse()
            body_statements.extend(parsed.get("statements", []))
            position += 1

        return body_statements

    def parse(self):
        program = {
            "type": "Program",
            "statements": []
        }

        while self.position < len(self.tokens):
            token = self.tokens[self.position]

            if token[0] == "START":
                program["statements"].append({
                    "type": "Start"
                })

            elif token[0] == "END":
                program["statements"].append({
                    "type": "End"
                })

            elif token[0] == "STEP":
                instruction = re.sub(r'^Step\s+\d+:\s*', '', token[2].strip(), flags=re.IGNORECASE)

                # RUNTIME MEASUREMENT - START
                if re.search(r'^Start runtime timer$', instruction, re.IGNORECASE):
                    program["statements"].append({"type": "RuntimeStart"})

                # RUNTIME MEASUREMENT - STOP
                elif re.search(r'^Stop runtime timer and assign the result to "([^"]+)"$', instruction, re.IGNORECASE):
                    match = re.search(r'^Stop runtime timer and assign the result to "([^"]+)"$', instruction, re.IGNORECASE)
                    program["statements"].append({"type": "RuntimeStop", "result": match.group(1)})

                # RUNTIME MEASUREMENT - DISPLAY
                elif re.search(r'^Display the runtime$', instruction, re.IGNORECASE):
                    program["statements"].append({"type": "RuntimeDisplay"})

                # EXCEPTION HANDLING - TRY
                if re.search(r'^Start a try block$', instruction, re.IGNORECASE):
                    program["statements"].append({"type": "Try"})

                # EXCEPTION HANDLING - CATCH
                elif re.search(r'^Catch the exception(?: as "([A-Za-z_][A-Za-z0-9_]*)")?$', instruction, re.IGNORECASE):
                    match = re.search(
                        r'^Catch the exception(?: as "([A-Za-z_][A-Za-z0-9_]*)")?$',
                        instruction,
                        re.IGNORECASE
                    )
                    program["statements"].append({
                        "type": "Catch",
                        "variable": match.group(1)
                    })

                # EXCEPTION HANDLING - FINALLY
                elif re.search(r'^Finally$', instruction, re.IGNORECASE):
                    program["statements"].append({"type": "Finally"})

                # EXCEPTION HANDLING - END TRY
                elif re.search(r'^End the try block$', instruction, re.IGNORECASE):
                    program["statements"].append({"type": "EndTry"})

                # EXCEPTION HANDLING - THROW
                elif re.search(r'^Throw an exception with message (.+)$', instruction, re.IGNORECASE):
                    match = re.search(
                        r'^Throw an exception with message (.+)$',
                        instruction,
                        re.IGNORECASE
                    )
                    program["statements"].append({
                        "type": "Throw",
                        "message": match.group(1).strip()
                    })

                # Define class / abstract class
                interface_match = re.search(
                    r'Define an interface named\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                )
                abstract_class_match = re.search(
                    r'Define an abstract class named\s+"([^"]+)"(?:\s+inheriting from\s+(.+))?',
                    instruction,
                    re.IGNORECASE
                )
                class_match = re.search(
                    r'Define a class named\s+"([^"]+)"(?:\s+inheriting from\s+(.+))?(?:\s+implementing interface\s+"([^"]+)")?',
                    instruction,
                    re.IGNORECASE
                )

                if interface_match:
                    class_match = interface_match
                    is_abstract_class = True
                    is_interface = True
                elif abstract_class_match:
                    class_match = abstract_class_match
                    is_abstract_class = True
                    is_interface = False
                else:
                    is_abstract_class = False
                    is_interface = False

                if class_match:
                    class_name = class_match.group(1)
                    parent_text = class_match.group(2) if class_match.lastindex and class_match.lastindex >= 2 else None
                    implemented_interface = class_match.group(3) if (not interface_match and class_match.lastindex and class_match.lastindex >= 3) else None
                    parent_classes = []
                    if parent_text:
                        parent_classes = [p.strip().strip('"') for p in re.split(r'\s+and\s+', parent_text, flags=re.IGNORECASE)]
                        for parent in parent_classes:
                            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', parent):
                                raise SyntaxError(f'Invalid parent class name: "{parent}".')
                    parent_class = parent_classes[0] if parent_classes else None

                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', class_name):
                        raise SyntaxError(
                            f'Invalid class name: "{class_name}".'
                        )

                    if any(
                        statement.get("type") == "Class"
                        and statement.get("name") == class_name
                        for statement in program["statements"]
                    ):
                        raise SyntaxError(
                            f'Class "{class_name}" is already defined.'
                        )

                    end_position = None

                    for search_position in range(
                        self.position + 1,
                        len(self.tokens)
                    ):
                        search_token = self.tokens[search_position]

                        if search_token[0] != "STEP":
                            continue

                        search_instruction = re.sub(
                            r'^Step\s+\d+:\s*',
                            '',
                            search_token[2].strip(),
                            flags=re.IGNORECASE
                        )

                        if re.search(
                            r'End the class',
                            search_instruction,
                            re.IGNORECASE
                        ):
                            end_position = search_position
                            break

                    if end_position is None:
                        raise SyntaxError(
                            f'Class "{class_name}" is missing "End the class".'
                        )

                    body_tokens = self.tokens[self.position + 1:end_position]
                    class_body = self.parse_class_body(body_tokens, class_name)

                    class_statement = {
                        "type": "Class",
                        "name": class_name,
                        "body": class_body
                    }
                    if is_abstract_class:
                        class_statement["abstract"] = True
                    if is_interface:
                        class_statement["interface"] = True
                    if implemented_interface:
                        class_statement["interfaces"] = [implemented_interface]
                    if parent_classes:
                        class_statement["parents"] = parent_classes
                        if len(parent_classes) == 1:
                            class_statement["parent"] = parent_classes[0]

                    program["statements"].append(class_statement)
                    self.position = end_position

                # Create object from class with constructor arguments
                object_with_args_match = re.search(
                    r'Create an object of class\s+"([^"]+)"\s+with\s+(.+?)\s+and assign it to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                )

                if object_with_args_match:
                    class_name = object_with_args_match.group(1)
                    argument_text = object_with_args_match.group(2).strip()
                    object_name = object_with_args_match.group(3)

                    class_statement = next(
                        (statement for statement in program["statements"]
                         if statement.get("type") == "Class"
                         and statement.get("name") == class_name),
                        None
                    )
                    if class_statement is None:
                        raise SyntaxError(f'Class "{class_name}" is not defined.')

                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', object_name):
                        raise SyntaxError(f'Invalid object name: "{object_name}".')

                    arguments = re.findall(
                        r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*',
                        argument_text
                    )
                    arguments = [a for a in arguments if a.lower() != "and"]

                    arguments = [
                        argument.strip('"')
                        if argument.startswith('"')
                        and argument.endswith('"')
                        and argument.strip('"') in self.known_variables
                        else argument
                        for argument in arguments
                    ]

                    constructor = next(
                        (member for member in class_statement.get("body", [])
                         if member.get("type") == "Constructor"),
                        None
                    )
                    if constructor is None and arguments:
                        raise SyntaxError(
                            f'Class "{class_name}" does not define a constructor with parameters.'
                        )
                    if constructor is not None:
                        parameters = constructor.get("parameters", [])
                        defaults = constructor.get("defaults", {})
                        required_count = len(parameters) - len(defaults)
                        if len(arguments) < required_count or len(arguments) > len(parameters):
                            raise SyntaxError(
                                f'Constructor for class "{class_name}" expects '
                                f'{required_count} to {len(parameters)} arguments but got {len(arguments)}.'
                            )

                    program["statements"].append({
                        "type": "ObjectCreation",
                        "class": class_name,
                        "object": object_name,
                        "args": arguments
                    })

                # Create object without constructor arguments
                elif re.search(
                    r'Create an object of class\s+"([^"]+)"\s+and assign it to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    object_match = re.search(
                        r'Create an object of class\s+"([^"]+)"\s+and assign it to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    class_name = object_match.group(1)
                    object_name = object_match.group(2)

                    class_statement = next(
                        (statement for statement in program["statements"]
                         if statement.get("type") == "Class"
                         and statement.get("name") == class_name),
                        None
                    )
                    if class_statement is None:
                        raise SyntaxError(f'Class "{class_name}" is not defined.')
                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', object_name):
                        raise SyntaxError(f'Invalid object name: "{object_name}".')

                    constructor = next(
                        (member for member in class_statement.get("body", [])
                         if member.get("type") == "Constructor"),
                        None
                    )
                    if constructor is not None:
                        parameters = constructor.get("parameters", [])
                        defaults = constructor.get("defaults", {})
                        required_count = len(parameters) - len(defaults)
                        if required_count > 0:
                            raise SyntaxError(
                                f'Constructor for class "{class_name}" expects '
                                f'{required_count} to {len(parameters)} arguments but got 0.'
                            )

                    program["statements"].append({
                        "type": "ObjectCreation",
                        "class": class_name,
                        "object": object_name,
                        "args": []
                    })

                # Update a property of an object
                elif re.search(
                    r'Set the property\s+"([^"]+)"\s+of object\s+"([^"]+)"\s+to\s+(.+)',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Set the property\s+"([^"]+)"\s+of object\s+"([^"]+)"\s+to\s+(.+)',
                        instruction,
                        re.IGNORECASE
                    )
                    value = match.group(3).strip()
                    if value.startswith('"') and value.endswith('"'):
                        value = value
                    program["statements"].append({
                        "type": "ObjectPropertyUpdate",
                        "property": match.group(1),
                        "object": match.group(2),
                        "value": value
                    })

                # Access a property of an object and assign the result
                elif re.search(
                    r'Get the property\s+"([^"]+)"\s+of object\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get the property\s+"([^"]+)"\s+of object\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    program["statements"].append({
                        "type": "ObjectPropertyAccess",
                        "property": match.group(1),
                        "object": match.group(2),
                        "result": match.group(3)
                    })

                # Get class variable
                elif re.search(
                    r'Get the class variable "([^"]+)" of class "([^"]+)" and assign the result to "([^"]+)"',
                    instruction, re.IGNORECASE
                ):
                    match = re.search(r'Get the class variable "([^"]+)" of class "([^"]+)" and assign the result to "([^"]+)"', instruction, re.IGNORECASE)
                    program["statements"].append({
                        "type": "ClassVariableAccess",
                        "name": match.group(1),
                        "class": match.group(2),
                        "result": match.group(3)
                    })

                # Display class variable
                elif re.search(
                    r'Display the class variable "([^"]+)" of class "([^"]+)"',
                    instruction, re.IGNORECASE
                ):
                    match = re.search(r'Display the class variable "([^"]+)" of class "([^"]+)"', instruction, re.IGNORECASE)
                    program["statements"].append({
                        "type": "ClassVariableDisplay",
                        "name": match.group(1),
                        "class": match.group(2)
                    })

                # Object equality / comparison
                elif re.search(
                    r'Compare objects "([^"]+)" and "([^"]+)" for equality and assign the result to "([^"]+)"',
                    instruction, re.IGNORECASE
                ):
                    match = re.search(
                        r'Compare objects "([^"]+)" and "([^"]+)" for equality and assign the result to "([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    program["statements"].append({
                        "type": "ObjectEquality",
                        "left": match.group(1),
                        "right": match.group(2),
                        "result": match.group(3)
                    })

                # Getters / setters can be declared at class level
                # Call a static method on a class
                elif re.search(
                    r'Call the static method "([^"]+)" of class "([^"]+)"(?: with (.+?))?(?: and assign the result to "([^"]+)")?$',
                    instruction, re.IGNORECASE
                ):
                    match = re.search(
                        r'Call the static method "([^"]+)" of class "([^"]+)"(?: with (.+?))?(?: and assign the result to "([^"]+)")?$',
                        instruction, re.IGNORECASE
                    )
                    arguments = []
                    if match.group(3):
                        arguments = re.findall(r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*', match.group(3))
                        arguments = [a for a in arguments if a.lower() != "and"]
                    program["statements"].append({"type":"StaticMethodCall","class":match.group(2),"method":match.group(1),"args":arguments,"result":match.group(4)})

                # Call a method on an object and assign the result
                elif re.search(
                    r'Call the method\s+"([^"]+)"\s+on object\s+"([^"]+)"(?:\s+with\s+(.+?))?\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Call the method\s+"([^"]+)"\s+on object\s+"([^"]+)"(?:\s+with\s+(.+?))?\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    arguments = []
                    if match.group(3):
                        arguments = re.findall(
                            r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*',
                            match.group(3)
                        )
                        arguments = [a for a in arguments if a.lower() != "and"]
                        object_names = {
                            s.get("object") for s in program["statements"]
                            if s.get("type") == "ObjectCreation"
                        }
                        arguments = [
                            a.strip('"') if a.startswith('"') and a.endswith('"') and a.strip('"') in object_names else a
                            for a in arguments
                        ]
                    program["statements"].append({
                        "type": "MethodCall",
                        "method": match.group(1),
                        "object": match.group(2),
                        "args": arguments,
                        "result": match.group(4)
                    })

                # Display a property of an object
                elif re.search(
                    r'Display the property\s+"([^"]+)"\s+of object\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Display the property\s+"([^"]+)"\s+of object\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    program["statements"].append({
                        "type": "ObjectPropertyDisplay",
                        "property": match.group(1),
                        "object": match.group(2)
                    })

                # Call a method on an object
                elif re.search(
                    r'Call the method\s+"([^"]+)"\s+on object\s+"([^"]+)"(?:\s+with\s+(.+))?',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Call the method\s+"([^"]+)"\s+on object\s+"([^"]+)"(?:\s+with\s+(.+))?',
                        instruction,
                        re.IGNORECASE
                    )
                    arguments = []
                    if match.group(3):
                        arguments = re.findall(
                            r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*',
                            match.group(3)
                        )
                        arguments = [a for a in arguments if a.lower() != "and"]
                        object_names = {
                            s.get("object") for s in program["statements"]
                            if s.get("type") == "ObjectCreation"
                        }
                        arguments = [
                            a.strip('"') if a.startswith('"') and a.endswith('"') and a.strip('"') in object_names else a
                            for a in arguments
                        ]
                    program["statements"].append({
                        "type": "MethodCall",
                        "method": match.group(1),
                        "object": match.group(2),
                        "args": arguments
                    })

                # Define function with parameters
                function_match = re.search(
                    r'Define a function named\s+"([^"]+)"\s+with parameter(?:s)?\s+(.+)',
                    instruction,
                    re.IGNORECASE
                )

                if function_match:
                    function_name = function_match.group(1)

                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', function_name):
                        raise SyntaxError(
                            f'Invalid function name: "{function_name}".'
                        )

                    if any(
                        statement.get("type") == "Function"
                        and statement.get("name") == function_name
                        for statement in program["statements"]
                    ):
                        raise SyntaxError(
                            f'Function "{function_name}" is already defined.'
                        )

                    parameter_text = function_match.group(2).strip()

                    return_type = None
                    return_type_match = re.search(
                        r'\s+and\s+return type\s+(integer|string|decimal|boolean)\s*$',
                        parameter_text,
                        re.IGNORECASE
                    )
                    if return_type_match:
                        return_type = return_type_match.group(1).lower()
                        parameter_text = parameter_text[:return_type_match.start()].strip()

                    parameter_values, parameter_types, defaults = self.parse_parameter_declarations(
                        parameter_text
                    )

                    for parameter in parameter_values:
                        if not re.fullmatch(
                            r'[A-Za-z_][A-Za-z0-9_]*',
                            parameter
                        ):
                            raise SyntaxError(
                                f'Invalid function parameter name: "{parameter}".'
                            )

                    if len(parameter_values) != len(set(parameter_values)):
                        seen_parameters = set()
                        for parameter in parameter_values:
                            if parameter in seen_parameters:
                                raise SyntaxError(
                                    f'Function "{function_name}" has duplicate parameter "{parameter}".'
                                )
                            seen_parameters.add(parameter)

                    parameters = parameter_values

                    default_seen = False
                    for parameter in parameters:
                        if parameter in defaults:
                            default_seen = True
                        elif default_seen:
                            raise SyntaxError(
                                f'Function "{function_name}" has a required parameter "{parameter}" after a default parameter.'
                            )

                    # Validate default values against declared parameter types.
                    for parameter, default_value in defaults.items():
                        expected_type = parameter_types.get(parameter)
                        if expected_type:
                            actual_type = self.infer_argument_type(default_value)
                            if actual_type is not None and actual_type != expected_type:
                                raise SyntaxError(
                                    f'Function "{function_name}" parameter "{parameter}" expects '
                                    f'{expected_type} but default value is {actual_type}.'
                                )

                    end_position = None

                    for search_position in range(
                        self.position + 1,
                        len(self.tokens)
                    ):
                        search_token = self.tokens[search_position]

                        if search_token[0] != "STEP":
                            continue

                        search_instruction = search_token[2].strip()

                        if re.search(
                            r'End the function',
                            search_instruction,
                            re.IGNORECASE
                        ):
                            end_position = search_position
                            break

                    if end_position is None:
                        raise SyntaxError(
                            f'Function "{function_name}" is missing "End the function".'
                        )

                    body_tokens = self.tokens[
                        self.position + 1:end_position
                    ]

                    body_program = Parser(
                        body_tokens,
                        known_variables=parameters,
                        inside_function=True
                    ).parse()

                    function_statement = {
                        "type": "Function",
                        "name": function_name,
                        "parameters": parameters,
                        "body": body_program["statements"]
                    }

                    if defaults:
                        function_statement["defaults"] = defaults

                    if parameter_types:
                        function_statement["parameter_types"] = parameter_types

                    if return_type:
                        self.validate_return_type(
                            function_name,
                            return_type,
                            body_program["statements"],
                            parameter_types
                        )
                        function_statement["return_type"] = return_type

                    program["statements"].append(function_statement)

                    self.position = end_position

                # Define function without parameters
                elif re.search(
                    r'Define a function named\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    function_match = re.search(
                        r'Define a function named\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    function_name = function_match.group(1)

                    return_type = None
                    return_type_match = re.search(
                        r'with return type\s+(integer|string|decimal|boolean)\s*$',
                        instruction,
                        re.IGNORECASE
                    )
                    if return_type_match:
                        return_type = return_type_match.group(1).lower()

                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', function_name):
                        raise SyntaxError(
                            f'Invalid function name: "{function_name}".'
                        )

                    if any(
                        statement.get("type") == "Function"
                        and statement.get("name") == function_name
                        for statement in program["statements"]
                    ):
                        raise SyntaxError(
                            f'Function "{function_name}" is already defined.'
                        )

                    end_position = None

                    for search_position in range(
                        self.position + 1,
                        len(self.tokens)
                    ):
                        search_token = self.tokens[search_position]

                        if search_token[0] != "STEP":
                            continue

                        search_instruction = search_token[2].strip()

                        if re.search(
                            r'End the function',
                            search_instruction,
                            re.IGNORECASE
                        ):
                            end_position = search_position
                            break

                    if end_position is None:
                        raise SyntaxError(
                            f'Function "{function_name}" is missing "End the function".'
                        )

                    body_tokens = self.tokens[
                        self.position + 1:end_position
                    ]

                    body_program = Parser(
                        body_tokens,
                        inside_function=True
                    ).parse()

                    function_statement = {
                        "type": "Function",
                        "name": function_name,
                        "parameters": [],
                        "body": body_program["statements"]
                    }

                    if return_type:
                        self.validate_return_type(
                            function_name,
                            return_type,
                            body_program["statements"],
                            {}
                        )
                        function_statement["return_type"] = return_type

                    program["statements"].append(function_statement)

                    self.position = end_position

                # Call function without arguments and assign the result
                elif re.fullmatch(
                    r'(?:Step\s+\d+:\s*)?Call the function\s+"([^"]+)"\s+with no arguments\s*,?\s*and\s+assign\s+the\s+result\s+to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    call_match = re.fullmatch(
                        r'(?:Step\s+\d+:\s*)?Call the function\s+"([^"]+)"\s+with no arguments\s*,?\s*and\s+assign\s+the\s+result\s+to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    function_name = call_match.group(1)
                    arguments = []

                    function_statement = self.get_function_statement(program, function_name)

                    if function_statement is None:
                        raise SyntaxError(
                            f'Function "{function_name}" is not defined.'
                        )

                    if function_statement:
                        defaults_for_function = function_statement.get("defaults", {})
                        function_parameters = function_statement.get("parameters", [])
                        required_count = len(function_parameters) - len(defaults_for_function)

                        if len(arguments) < required_count:
                            raise SyntaxError(
                                f'Function "{function_name}" expects '
                                f'{required_count} to {len(function_parameters)} arguments but got '
                                f'{len(arguments)}.'
                            )

                        self.validate_argument_types(
                            function_name,
                            function_statement,
                            arguments
                        )

                    program["statements"].append({
                        "type": "FunctionCall",
                        "name": function_name,
                        "args": arguments,
                        "result": call_match.group(2)
                    })

                # Call function without arguments
                elif re.fullmatch(
                    r'(?:Step\s+\d+:\s*)?Call the function\s+"([^"]+)"\s+with no arguments',
                    instruction,
                    re.IGNORECASE
                ):
                    call_match = re.fullmatch(
                        r'(?:Step\s+\d+:\s*)?Call the function\s+"([^"]+)"\s+with no arguments',
                        instruction,
                        re.IGNORECASE
                    )
                    function_name = call_match.group(1)
                    arguments = []

                    function_statement = self.get_function_statement(program, function_name)

                    if function_statement is None:
                        raise SyntaxError(
                            f'Function "{function_name}" is not defined.'
                        )

                    if function_statement:
                        defaults_for_function = function_statement.get("defaults", {})
                        function_parameters = function_statement.get("parameters", [])
                        required_count = len(function_parameters) - len(defaults_for_function)

                        if len(arguments) < required_count:
                            raise SyntaxError(
                                f'Function "{function_name}" expects '
                                f'{required_count} to {len(function_parameters)} arguments but got '
                                f'{len(arguments)}.'
                            )

                        self.validate_argument_types(
                            function_name,
                            function_statement,
                            arguments
                        )

                    program["statements"].append({
                        "type": "FunctionCall",
                        "name": function_name,
                        "args": arguments
                    })

                # Call function with arguments and assign the result
                elif re.search(
                    r'Call the function\s+"([^"]+)"\s+with\s+(.+?),\s*and\s+assign\s+the\s+result\s+to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    call_match = re.search(
                        r'Call the function\s+"([^"]+)"\s+with\s+(.+?),\s*and\s+assign\s+the\s+result\s+to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    function_name = call_match.group(1)
                    argument_text = call_match.group(2).strip()
                    result_variable = call_match.group(3)

                    arguments = re.findall(
                        r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*',
                        argument_text
                    )

                    arguments = [
                        argument for argument in arguments
                        if argument.lower() != "and"
                    ]

                    arguments = [
                        argument.strip('"')
                        if argument.startswith('"')
                        and argument.endswith('"')
                        and argument.strip('"') in self.known_variables
                        else argument
                        for argument in arguments
                    ]

                    # Validate argument count when the function definition is available.
                    function_statement = self.get_function_statement(program, function_name)
                    function_parameters = (
                        function_statement.get("parameters", [])
                        if function_statement else None
                    )

                    if function_parameters is None:
                        raise SyntaxError(
                            f'Function "{function_name}" is not defined.'
                        )

                    if function_parameters is not None:
                        function_statement = self.get_function_statement(program, function_name)
                        defaults_for_function = (
                            function_statement.get("defaults", {})
                            if function_statement else {}
                        )
                        required_count = len(function_parameters) - len(defaults_for_function)

                        if len(arguments) < required_count or len(arguments) > len(function_parameters):
                            expected_text = (
                                str(len(function_parameters))
                                if required_count == len(function_parameters)
                                else f'{required_count} to {len(function_parameters)}'
                            )
                            raise SyntaxError(
                                f'Function "{function_name}" expects '
                                f'{expected_text} arguments but got '
                                f'{len(arguments)}.'
                            )

                        self.validate_argument_types(
                            function_name,
                            function_statement,
                            arguments
                        )

                    program["statements"].append({
                        "type": "FunctionCall",
                        "name": function_name,
                        "args": arguments,
                        "result": result_variable
                    })

                # Call function with arguments
                elif re.search(
                    r'Call the function\s+"([^"]+)"\s+with\s+(.+)',
                    instruction,
                    re.IGNORECASE
                ):
                    call_match = re.search(
                        r'Call the function\s+"([^"]+)"\s+with\s+(.+)',
                        instruction,
                        re.IGNORECASE
                    )

                    function_name = call_match.group(1)
                    argument_text = call_match.group(2).strip()

                    arguments = re.findall(
                        r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*',
                        argument_text
                    )

                    # NEW:
                    # Remove the separator word "and" from function arguments.
                    # Example:
                    # "Anbarasu" and 21 -> ["Anbarasu", 21]
                    #
                    # Existing argument parsing is preserved for all other values.
                    arguments = [
                        argument for argument in arguments
                        if argument.lower() != "and"
                    ]

                    arguments = [
                        argument.strip('"')
                        if argument.startswith('"')
                        and argument.endswith('"')
                        and argument.strip('"') in self.known_variables
                        else argument
                        for argument in arguments
                    ]

                    # Validate argument count when the function definition is available.
                    function_statement = self.get_function_statement(program, function_name)
                    function_parameters = (
                        function_statement.get("parameters", [])
                        if function_statement else None
                    )

                    if function_parameters is None:
                        raise SyntaxError(
                            f'Function "{function_name}" is not defined.'
                        )

                    if function_parameters is not None:
                        function_statement = self.get_function_statement(program, function_name)
                        defaults_for_function = (
                            function_statement.get("defaults", {})
                            if function_statement else {}
                        )
                        required_count = len(function_parameters) - len(defaults_for_function)

                        if len(arguments) < required_count or len(arguments) > len(function_parameters):
                            expected_text = (
                                str(len(function_parameters))
                                if required_count == len(function_parameters)
                                else f'{required_count} to {len(function_parameters)}'
                            )
                            raise SyntaxError(
                                f'Function "{function_name}" expects '
                                f'{expected_text} arguments but got '
                                f'{len(arguments)}.'
                            )

                        self.validate_argument_types(
                            function_name,
                            function_statement,
                            arguments
                        )

                    program["statements"].append({
                        "type": "FunctionCall",
                        "name": function_name,
                        "args": arguments
                    })

                # Call function without arguments
                elif re.fullmatch(
                    r'(?:Step\s+\d+:\s*)?Call the function\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    call_match = re.fullmatch(
                        r'(?:Step\s+\d+:\s*)?Call the function\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    function_name = call_match.group(1)

                    function_statement = self.get_function_statement(program, function_name)

                    if function_statement is None:
                        raise SyntaxError(
                            f'Function "{function_name}" is not defined.'
                        )

                    program["statements"].append({
                        "type": "FunctionCall",
                        "name": function_name,
                        "args": []
                    })

                # Return value from function
                elif re.search(
                    r'Return the value of\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Return the value of\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        if not self.inside_function:
                            raise SyntaxError(
                                'Return statement is only allowed inside a function.'
                            )

                        program["statements"].append({
                            "type": "Return",
                            "variable": match.group(1)
                        })

                # End function is consumed while parsing the function body
                elif re.search(
                    r'End the function',
                    instruction,
                    re.IGNORECASE
                ):
                    pass

                # End class is consumed while parsing the class body
                elif re.search(
                    r'End the class',
                    instruction,
                    re.IGNORECASE
                ):
                    pass

                # Display text
                elif re.search(
                    r'Display\s+"([^"]*)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Display\s+"([^"]*)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Display",
                            "value": f'"{match.group(1)}"'
                        })

                # Input integer
                elif re.search(
                    r'Get the value for integer type',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'assign the variable\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Input",
                            "data_type": "integer",
                            "variable": match.group(1)
                        })

                # Input string
                elif re.search(
                    r'Get the value for string type',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'assign the variable\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Input",
                            "data_type": "string",
                            "variable": match.group(1)
                        })

                # Input decimal
                elif re.search(
                    r'Get the value for decimal type',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'assign the variable\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Input",
                            "data_type": "decimal",
                            "variable": match.group(1)
                        })

                # Input boolean
                elif re.search(
                    r'Get the value for boolean type',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'assign the variable\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Input",
                            "data_type": "boolean",
                            "variable": match.group(1)
                        })

                # Advanced expression
                # Absolute value
                elif re.search(r'^Calculate the absolute value of\s+', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Calculate the absolute value of\s+(.+?)\s+and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"MathOperation","operation":"abs","value":match.group(1).strip(),"result":match.group(2)})

                # Minimum
                elif re.search(r'^Calculate the minimum of\s+', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Calculate the minimum of\s+(.+?)\s+and\s+(.+?)\s*,?\s*and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"MathOperation","operation":"min","left":match.group(1).strip(),"right":match.group(2).strip(),"result":match.group(3)})

                # Maximum
                elif re.search(r'^Calculate the maximum of\s+', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Calculate the maximum of\s+(.+?)\s+and\s+(.+?)\s*,?\s*and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"MathOperation","operation":"max","left":match.group(1).strip(),"right":match.group(2).strip(),"result":match.group(3)})

                # Round
                elif re.search(r'^Round\s+', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Round\s+(.+?)\s+to\s+(\d+)\s+decimal places\s*,?\s*and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"MathOperation","operation":"round","value":match.group(1).strip(),"digits":match.group(2),"result":match.group(3)})


                elif (
                    "Calculate" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Calculate\s+"(.+?)"\s+and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        expression = match.group(1).strip()
                        result = match.group(2)

                        program["statements"].append({
                            "type": "Expression",
                            "expression": expression,
                            "result": result
                        })

                # Direct assignment
                elif re.search(
                    r'Assign the value\s+(.+?)\s+to the variable\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Assign the value\s+(.+?)\s+to the variable\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        value = match.group(1).strip()
                        variable = match.group(2)

                        program["statements"].append({
                            "type": "Assignment",
                            "variable": variable,
                            "value": value
                        })

                # List range with optional step and expression support
                elif re.search(
                    r'Create a list of numbers from\s+(.+?)\s+to\s+(.+?)(?:\s+with a step of\s+(.+?))?\s+and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Create a list of numbers from\s+(.+?)\s+to\s+(.+?)(?:\s+with a step of\s+(.+?))?\s+and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        statement = {
                            "type": "ListRange",
                            "start": match.group(1).strip(),
                            "end": match.group(2).strip(),
                            "result": match.group(4)
                        }

                        if match.group(3) is not None:
                            statement["step"] = match.group(3).strip()

                        program["statements"].append(statement)

                # Dictionary set / add key
                elif re.search(
                    r'Set the key "([^"]+)" to (.+?) in the dictionary "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Set the key "([^"]+)" to (.+?) in the dictionary "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionarySet",
                            "key": match.group(1),
                            "value": match.group(2).strip(),
                            "dictionary": match.group(3)
                        })

                # Dictionary clear
                elif re.search(
                    r'Clear the dictionary "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Clear the dictionary "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryClear",
                            "dictionary": match.group(1)
                        })

                # Dictionary update / modify existing key
                elif re.search(
                    r'Update the key "([^"]+)" to (.+?) in the dictionary "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Update the key "([^"]+)" to (.+?) in the dictionary "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryUpdate",
                            "key": match.group(1),
                            "value": match.group(2).strip(),
                            "dictionary": match.group(3)
                        })

                # Dictionary remove / delete key
                elif re.search(
                    r'Remove the key "([^"]+)" from the dictionary "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Remove the key "([^"]+)" from the dictionary "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryRemove",
                            "key": match.group(1),
                            "dictionary": match.group(2)
                        })

                # Dictionary contains / key exists
                elif re.search(
                    r'Check whether the key "([^"]+)" exists in the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Check whether the key "([^"]+)" exists in the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryContains",
                            "key": match.group(1),
                            "dictionary": match.group(2),
                            "result": match.group(3)
                        })

                # Dictionary length
                elif re.search(
                    r'Get the length of the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get the length of the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryLength",
                            "dictionary": match.group(1),
                            "result": match.group(2)
                        })

                # Dictionary items / key-value pairs
                elif re.search(
                    r'Get all the items from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get all the items from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryItems",
                            "dictionary": match.group(1),
                            "result": match.group(2)
                        })

                # Dictionary values
                elif re.search(
                    r'Get all the values from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get all the values from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryValues",
                            "dictionary": match.group(1),
                            "result": match.group(2)
                        })

                # Dictionary keys
                elif re.search(
                    r'Get all the keys from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get all the keys from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryKeys",
                            "dictionary": match.group(1),
                            "result": match.group(2)
                        })

                # Dictionary get / access value
                elif re.search(
                    r'Get the value for the key "([^"]+)" from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get the value for the key "([^"]+)" from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DictionaryGet",
                            "key": match.group(1),
                            "dictionary": match.group(2),
                            "result": match.group(3)
                        })

                # Dictionary copy
                elif re.search(
                    r'Copy the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Copy the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryCopy",
                            "dictionary": match.group(1),
                            "result": match.group(2)
                        })

                # Dictionary merge into existing dictionary
                elif re.search(
                    r'Merge the dictionary "([^"]+)" into the dictionary "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Merge the dictionary "([^"]+)" into the dictionary "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryMerge",
                            "source": match.group(1),
                            "target": match.group(2)
                        })

                # Dictionary merge into a new dictionary
                elif re.search(
                    r'Merge the dictionaries "([^"]+)" and "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Merge the dictionaries "([^"]+)" and "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryMergeNew",
                            "first": match.group(1),
                            "second": match.group(2),
                            "result": match.group(3)
                        })

                # Dictionary pop
                elif re.search(
                    r'Pop the key "([^"]+)" from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Pop the key "([^"]+)" from the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryPop",
                            "key": match.group(1),
                            "dictionary": match.group(2),
                            "result": match.group(3)
                        })

                # Dictionary pop with default
                elif re.search(
                    r'Pop the key "([^"]+)" from the dictionary "([^"]+)" with default (.+?) and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Pop the key "([^"]+)" from the dictionary "([^"]+)" with default (.+?) and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryPopDefault",
                            "key": match.group(1),
                            "dictionary": match.group(2),
                            "default": match.group(3).strip(),
                            "result": match.group(4)
                        })

                # Dictionary get with default
                elif re.search(
                    r'Get the value for the key "([^"]+)" from the dictionary "([^"]+)" with default (.+?) and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get the value for the key "([^"]+)" from the dictionary "([^"]+)" with default (.+?) and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryGetDefault",
                            "key": match.group(1),
                            "dictionary": match.group(2),
                            "default": match.group(3).strip(),
                            "result": match.group(4)
                        })

                # Dictionary set default
                elif re.search(
                    r'Set the default value for the key "([^"]+)" to (.+?) in the dictionary "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Set the default value for the key "([^"]+)" to (.+?) in the dictionary "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionarySetDefault",
                            "key": match.group(1),
                            "value": match.group(2).strip(),
                            "dictionary": match.group(3)
                        })

                # Dictionary value exists
                elif re.search(
                    r'Check whether the value (.+?) exists in the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Check whether the value (.+?) exists in the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryValueContains",
                            "value": match.group(1).strip(),
                            "dictionary": match.group(2),
                            "result": match.group(3)
                        })

                # Dictionary filter
                elif re.search(
                    r'Filter the dictionary "([^"]+)" for values (greater than|less than|equal to|not equal to) (.+?) and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Filter the dictionary "([^"]+)" for values (greater than|less than|equal to|not equal to) (.+?) and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        op_map = {
                            "greater than": ">",
                            "less than": "<",
                            "equal to": "==",
                            "not equal to": "!="
                        }
                        program["statements"].append({
                            "type": "DictionaryFilter",
                            "dictionary": match.group(1),
                            "operator": op_map[match.group(2).lower()],
                            "value": match.group(3).strip(),
                            "result": match.group(4)
                        })

                # Dictionary map / transform values
                elif re.search(
                    r'Map the values in the dictionary "([^"]+)" by (adding|subtracting|multiplying by|dividing by) (.+?) and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Map the values in the dictionary "([^"]+)" by (adding|subtracting|multiplying by|dividing by) (.+?) and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        op_map = {
                            "adding": "+",
                            "subtracting": "-",
                            "multiplying by": "*",
                            "dividing by": "/"
                        }
                        program["statements"].append({
                            "type": "DictionaryMap",
                            "dictionary": match.group(1),
                            "operation": op_map[match.group(2).lower()],
                            "value": match.group(3).strip(),
                            "result": match.group(4)
                        })

                # Dictionary inversion
                elif re.search(
                    r'Invert the keys and values of the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Invert the keys and values of the dictionary "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryInvert",
                            "dictionary": match.group(1),
                            "result": match.group(2)
                        })

                # Dictionary sort
                elif re.search(
                    r'Sort the dictionary "([^"]+)" by (key|value) and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Sort the dictionary "([^"]+)" by (key|value) and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionarySort",
                            "dictionary": match.group(1),
                            "by": match.group(2).lower(),
                            "result": match.group(3)
                        })

                # Dictionary from key and value lists
                elif re.search(
                    r'Create a dictionary from the keys in the list "([^"]+)" and the values in the list "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Create a dictionary from the keys in the list "([^"]+)" and the values in the list "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryFromLists",
                            "keys": match.group(1),
                            "values": match.group(2),
                            "result": match.group(3)
                        })

                # Dictionary from key-value pair list
                elif re.search(
                    r'Create a dictionary from the key-value pairs in the list "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Create a dictionary from the key-value pairs in the list "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DictionaryFromPairs",
                            "pairs": match.group(1),
                            "result": match.group(2)
                        })

                # Dictionary create
                elif re.search(
                    r'Create a dictionary and assign it to the variable\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Create a dictionary and assign it to the variable\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Dictionary",
                            "variable": match.group(1)
                        })

                # Create list
                elif re.search(
                    r'Create a list',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Create a list\s+(.+?)\s+and assign it to the variable\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        values = match.group(1).strip()
                        variable = match.group(2)

                        program["statements"].append({
                            "type": "List",
                            "values": values,
                            "variable": variable
                        })

                # List item access
                elif re.search(
                    r'Get the item at index\s+(.+?)\s+from the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get the item at index\s+(.+?)\s+from the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListItemAccess",
                            "index": match.group(1).strip(),
                            "list": match.group(2),
                            "result": match.group(3)
                        })

                # List length
                elif (
                    "Get the length of the list" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Get the length of the list\s+"([^"]+)"\s+and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListLength",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List append
                elif re.search(
                    r'Append the value\s+(.+?)\s+to the list\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Append the value\s+(.+?)\s+to the list\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListAppend",
                            "value": match.group(1).strip(),
                            "list": match.group(2)
                        })

                # List insert
                elif re.search(
                    r'Insert the value\s+(.+?)\s+at index\s+(.+?)\s+into the list\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Insert the value\s+(.+?)\s+at index\s+(.+?)\s+into the list\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListInsert",
                            "value": match.group(1).strip(),
                            "index": match.group(2).strip(),
                            "list": match.group(3)
                        })

                # List remove
                elif re.search(
                    r'Remove the value\s+(.+?)\s+from the list\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Remove the value\s+(.+?)\s+from the list\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListRemove",
                            "value": match.group(1).strip(),
                            "list": match.group(2)
                        })

                # List pop
                elif re.search(
                    r'Remove and return the last item from the list "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Remove and return the last item from the list "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListPop",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List clear
                elif re.search(
                    r'Clear the list "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Clear the list "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListClear",
                            "list": match.group(1)
                        })

                # List index of
                elif re.search(
                    r'Find the index of the value\s+(.+?)\s+in the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Find the index of the value\s+(.+?)\s+in the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListIndexOf",
                            "value": match.group(1).strip(),
                            "list": match.group(2),
                            "result": match.group(3)
                        })

                # List contains
                elif re.search(
                    r'Find whether the value\s+(.+?)\s+exists in the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Find whether the value\s+(.+?)\s+exists in the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListContains",
                            "value": match.group(1).strip(),
                            "list": match.group(2),
                            "result": match.group(3)
                        })

                # List find / search
                elif re.search(
                    r'Find the value\s+(.+?)\s+in the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Find the value\s+(.+?)\s+in the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListFind",
                            "value": match.group(1).strip(),
                            "list": match.group(2),
                            "result": match.group(3)
                        })

                # List unique / remove duplicates
                elif re.search(
                    r'Remove duplicate values from the list "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Remove duplicate values from the list "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListUnique",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List zip / combine
                elif re.search(
                    r'Zip the lists "([^"]+)" and "([^"]+)" together and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Zip the lists "([^"]+)" and "([^"]+)" together and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListZip",
                            "first": match.group(1),
                            "second": match.group(2),
                            "result": match.group(3)
                        })

                # List enumerate
                elif re.search(
                    r'Enumerate the items in the list "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Enumerate the items in the list "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListEnumerate",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List filter
                elif re.search(
                    r'Filter the list "([^"]+)" for values (greater than or equal to|less than or equal to|greater than|less than|equal to|not equal to)\s+(.+?) and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Filter the list "([^"]+)" for values (greater than or equal to|less than or equal to|greater than|less than|equal to|not equal to)\s+(.+?) and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        operator_map = {
                            "greater than": ">",
                            "less than": "<",
                            "greater than or equal to": ">=",
                            "less than or equal to": "<=",
                            "equal to": "==",
                            "not equal to": "!="
                        }

                        program["statements"].append({
                            "type": "ListFilter",
                            "list": match.group(1),
                            "operator": operator_map[match.group(2).lower()],
                            "value": match.group(3).strip(),
                            "result": match.group(4)
                        })

                # List map / transform
                elif re.search(
                    r'Map each item in the list "([^"]+)" by (adding|subtracting|multiplying by|dividing by)\s+(.+?) and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Map each item in the list "([^"]+)" by (adding|subtracting|multiplying by|dividing by)\s+(.+?) and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        operation_map = {
                            "adding": "+",
                            "subtracting": "-",
                            "multiplying by": "*",
                            "dividing by": "/"
                        }

                        program["statements"].append({
                            "type": "ListMap",
                            "list": match.group(1),
                            "operation": operation_map[match.group(2).lower()],
                            "value": match.group(3).strip(),
                            "result": match.group(4)
                        })

                # List any
                elif re.search(
                    r'Check whether any item in the list "([^"]+)" is true and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Check whether any item in the list "([^"]+)" is true and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListAny",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List all
                elif re.search(
                    r'Check whether all items in the list "([^"]+)" are true and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Check whether all items in the list "([^"]+)" are true and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListAll",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List reverse
                elif re.search(
                    r'Reverse the list "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Reverse the list "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListReverse",
                            "list": match.group(1)
                        })

                # List sort
                elif re.search(
                    r'Sort the list "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Sort the list "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListSort",
                            "list": match.group(1)
                        })

                # List copy
                elif re.search(
                    r'Copy the list "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Copy the list "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListCopy",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List extend
                elif re.search(
                    r'Extend the list "([^"]+)" with the list "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Extend the list "([^"]+)" with the list "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListExtend",
                            "list": match.group(1),
                            "source": match.group(2)
                        })

                # List slice
                elif re.search(
                    r'Get the items from index\s+(.+?)\s+to index\s+(.+?)\s+from the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Get the items from index\s+(.+?)\s+to index\s+(.+?)\s+from the list\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListSlice",
                            "start": match.group(1).strip(),
                            "end": match.group(2).strip(),
                            "list": match.group(3),
                            "result": match.group(4)
                        })

                # List join
                elif re.search(
                    r'Join the items in the list\s+"([^"]+)"\s+using\s+(.+?)\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Join the items in the list\s+"([^"]+)"\s+using\s+(.+?)\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListJoin",
                            "list": match.group(1),
                            "separator": match.group(2).strip(),
                            "result": match.group(3)
                        })

                # List split
                elif re.search(
                    r'Split the text\s+(.+?)\s+using\s+(.+?)\s+and assign the result to\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Split the text\s+(.+?)\s+using\s+(.+?)\s+and assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListSplit",
                            "text": match.group(1).strip(),
                            "separator": match.group(2).strip(),
                            "result": match.group(3)
                        })

                # List min
                elif re.search(
                    r'Find the minimum value in the list "([^"]+)" and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Find the minimum value in the list "([^"]+)" and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListMin",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List empty
                elif re.search(
                    r'Check whether the list "([^"]+)" is empty and assign the result to "([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Check whether the list "([^"]+)" is empty and assign the result to "([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListEmpty",
                            "list": match.group(1),
                            "result": match.group(2)
                        })

                # List item update
                elif re.search(
                    r'Set index\s+(.+?)\s+of the list\s+"([^"]+)"\s+to\s+(.+)',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Set index\s+(.+?)\s+of the list\s+"([^"]+)"\s+to\s+(.+)',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ListItemUpdate",
                            "index": match.group(1).strip(),
                            "list": match.group(2),
                            "value": match.group(3).strip()
                        })

                # Increase
                elif re.search(
                    r'Increase\s+"([^"]+)"\s+by\s+(.+)',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Increase\s+"([^"]+)"\s+by\s+(.+)',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Increase",
                            "variable": match.group(1),
                            "value": match.group(2).strip()
                        })

                # Decrease
                elif re.search(
                    r'Decrease\s+"([^"]+)"\s+by\s+(.+)',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Decrease\s+"([^"]+)"\s+by\s+(.+)',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Decrease",
                            "variable": match.group(1),
                            "value": match.group(2).strip()
                        })

                # String concatenation
                elif (
                    "Concatenate" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Concatenate\s+"([^"]+)"\s+and\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "StringConcatenation",
                            "left": match.group(1),
                            "right": match.group(2),
                            "result": match.group(3)
                        })

                # String length
                elif (
                    "Find the length of" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Find the length of\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "StringLength",
                            "variable": match.group(1),
                            "result": match.group(2)
                        })

                # String uppercase
                elif (
                    "Convert" in instruction
                    and "to uppercase" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Convert\s+"([^"]+)"\s+to uppercase\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "StringUppercase",
                            "variable": match.group(1),
                            "result": match.group(2)
                        })

                # String lowercase
                elif (
                    "Convert" in instruction
                    and "to lowercase" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Convert\s+"([^"]+)"\s+to lowercase\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "StringLowercase",
                            "variable": match.group(1),
                            "result": match.group(2)
                        })

                # String replace
                elif (
                    "Replace" in instruction
                    and "with" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Replace\s+"([^"]+)"\s+with\s+"([^"]+)"\s+in\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "StringReplace",
                            "old": match.group(1),
                            "new": match.group(2),
                            "variable": match.group(3),
                            "result": match.group(4)
                        })

                # String contains
                elif (
                    "Check whether" in instruction
                    and "exists in" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Check whether\s+"([^"]+)"\s+exists in\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "StringContains",
                            "search": match.group(1),
                            "variable": match.group(2),
                            "result": match.group(3)
                        })

                # String starts with
                elif (
                    "starts with" in instruction.lower()
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Check whether the string\s+"([^"]+)"\s+starts with\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "StringStartsWith",
                            "variable": match.group(1),
                            "prefix": match.group(2),
                            "result": match.group(3)
                        })

                # String ends with
                elif (
                    "ends with" in instruction.lower()
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Check whether the string\s+"([^"]+)"\s+ends with\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "StringEndsWith",
                            "variable": match.group(1),
                            "suffix": match.group(2),
                            "result": match.group(3)
                        })

                # String find
                elif (
                    "Find the position of" in instruction
                    and "in the string" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Find the position of\s+"([^"]+)"\s+in the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "StringFind",
                            "search": match.group(1),
                            "variable": match.group(2),
                            "result": match.group(3)
                        })

                # String index
                elif (
                    "Find the index of" in instruction
                    and "in the string" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Find the index of\s+"([^"]+)"\s+in the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "StringIndex",
                            "search": match.group(1),
                            "variable": match.group(2),
                            "result": match.group(3)
                        })

                # String count
                elif (
                    "Count occurrences of" in instruction
                    and "in the string" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Count occurrences of\s+"([^"]+)"\s+in the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "StringCount",
                            "search": match.group(1),
                            "variable": match.group(2),
                            "result": match.group(3)
                        })

                # String trim
                elif re.search(r'^Trim the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Trim the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringTrim","variable":match.group(1),"result":match.group(2)})

                # String left trim
                elif re.search(r'^Left trim the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Left trim the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringLeftTrim","variable":match.group(1),"result":match.group(2)})

                # String right trim
                elif re.search(r'^Right trim the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Right trim the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringRightTrim","variable":match.group(1),"result":match.group(2)})

                # String split
                elif re.search(r'^Split the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Split the string\s+"([^"]+)"\s+using\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringSplit","variable":match.group(1),"separator":match.group(2),"result":match.group(3)})

                # String join
                elif re.search(r'^Join the list', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Join the list\s+"([^"]+)"\s+using\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringJoin","list":match.group(1),"separator":match.group(2),"result":match.group(3)})

                # String substring
                elif re.search(r'^Get the substring', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Get the substring from index\s+(.+?)\s+to\s+(.+?)\s+of the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringSubstring","start":match.group(1).strip(),"end":match.group(2).strip(),"variable":match.group(3),"result":match.group(4)})

                # String character access
                elif re.search(r'^Get the character at index', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Get the character at index\s+(.+?)\s+from the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringCharacter","index":match.group(1).strip(),"variable":match.group(2),"result":match.group(3)})

                # String reverse
                elif re.search(r'^Reverse the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Reverse the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringReverse","variable":match.group(1),"result":match.group(2)})

                # String repeat
                elif re.search(r'^Repeat the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Repeat the string\s+"([^"]+)"\s+(.+?)\s+times\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringRepeat","variable":match.group(1),"count":match.group(2).strip(),"result":match.group(3)})

                # String capitalize
                elif re.search(r'^Capitalize the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Capitalize the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringCapitalize","variable":match.group(1),"result":match.group(2)})

                # String title case
                elif re.search(r'^Convert the string.*title case', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Convert the string\s+"([^"]+)"\s+to title case\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringTitle","variable":match.group(1),"result":match.group(2)})

                # String swap case
                elif re.search(r'^Swap the case', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Swap the case of the string\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringSwapCase","variable":match.group(1),"result":match.group(2)})

                # String validation
                elif re.search(r'^Validate the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Validate the string\s+"([^"]+)"\s+as\s+(alphabetic|numeric|alphanumeric|digits|space|lowercase|uppercase)\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringValidation","variable":match.group(1),"validation":match.group(2).lower(),"result":match.group(3)})

                # String formatting
                elif re.search(r'^Format the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Format the string\s+"([^"]+)"\s+using variable\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringFormat","template":match.group(1),"variable":match.group(2),"result":match.group(3)})

                # String interpolation
                elif re.search(r'^Interpolate the string', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Interpolate the string\s+"([^"]+)"\s+using the variable\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"StringInterpolate","template":match.group(1),"variable":match.group(2),"result":match.group(3)})

                # File read
                elif re.search(r'^Read the file', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Read the file\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileRead",
                            "file": match.group(1),
                            "result": match.group(2)
                        })

                # File write
                elif re.search(r'^Write the value', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Write the value\s+(.+?)\s+to the file\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileWrite",
                            "value": match.group(1).strip(),
                            "file": match.group(2)
                        })

                # File append
                elif re.search(r'^Append the value', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Append the value\s+(.+?)\s+to the file\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileAppend",
                            "value": match.group(1).strip(),
                            "file": match.group(2)
                        })

                # File exists
                elif re.search(r'^Check whether the file', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Check whether the file\s+"([^"]+)"\s+exists and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileExists",
                            "file": match.group(1),
                            "result": match.group(2)
                        })

                # File delete
                elif re.search(r'^Delete the file', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Delete the file\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileDelete",
                            "file": match.group(1)
                        })

                # File size
                elif re.search(r'^Get the size of the file', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Get the size of the file\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileSize",
                            "file": match.group(1),
                            "result": match.group(2)
                        })

                # File rename
                elif re.search(r'^Rename the file', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Rename the file\s+"([^"]+)"\s+to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileRename",
                            "source": match.group(1),
                            "destination": match.group(2)
                        })

                # File copy
                elif re.search(r'^Copy the file', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Copy the file\s+"([^"]+)"\s+to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileCopy",
                            "source": match.group(1),
                            "destination": match.group(2)
                        })

                # File move
                elif re.search(r'^Move the file', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Move the file\s+"([^"]+)"\s+to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "FileMove",
                            "source": match.group(1),
                            "destination": match.group(2)
                        })

                # List files in directory
                elif re.search(r'^List the files in the directory', instruction, re.IGNORECASE):
                    match = re.search(
                        r'List the files in the directory\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({
                            "type": "DirectoryList",
                            "directory": match.group(1),
                            "result": match.group(2)
                        })

                # Basic type conversion: integer
                elif re.search(r'^Convert\s+.+\s+to\s+(integer|decimal|string|boolean)\b', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Convert\s+(.+?)\s+to integer\s*,?\s*and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"Convert","target_type":"integer","value":match.group(1).strip(),"result":match.group(2)})
                    else:
                        match = re.search(
                            r'Convert\s+(.+?)\s+to decimal\s*,?\s*and assign the result to\s+"([^"]+)"',
                            instruction, re.IGNORECASE
                        )
                        if match:
                            program["statements"].append({"type":"Convert","target_type":"decimal","value":match.group(1).strip(),"result":match.group(2)})
                        else:
                            match = re.search(
                                r'Convert\s+(.+?)\s+to string\s*,?\s*and assign the result to\s+"([^"]+)"',
                                instruction, re.IGNORECASE
                            )
                            if match:
                                program["statements"].append({"type":"Convert","target_type":"string","value":match.group(1).strip(),"result":match.group(2)})
                            else:
                                match = re.search(
                                    r'Convert\s+(.+?)\s+to boolean\s*,?\s*and assign the result to\s+"([^"]+)"',
                                    instruction, re.IGNORECASE
                                )
                                if match:
                                    program["statements"].append({"type":"Convert","target_type":"boolean","value":match.group(1).strip(),"result":match.group(2)})

                # Random integer
                elif re.search(r'^Generate a random integer between\s+', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Generate a random integer between\s+(.+?)\s+and\s+(.+?)\s+and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"RandomInteger","left":match.group(1).strip(),"right":match.group(2).strip(),"result":match.group(3)})

                # Current date
                elif re.search(r'^Get the current date', instruction, re.IGNORECASE):
                    match = re.search(r'Get the current date and assign the result to\s+"([^"]+)"', instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"CurrentDate","result":match.group(1)})

                # Current time
                elif re.search(r'^Get the current time', instruction, re.IGNORECASE):
                    match = re.search(r'Get the current time and assign the result to\s+"([^"]+)"', instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"CurrentTime","result":match.group(1)})

                # JSON encode
                elif re.search(r'^Convert the value of\s+', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Convert the value of\s+"([^"]+)"\s+to JSON\s+and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"JsonEncode","variable":match.group(1),"result":match.group(2)})

                # JSON decode
                elif re.search(r'^Parse the JSON string in\s+', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Parse the JSON string in\s+"([^"]+)"\s+and assign the result to\s+"([^"]+)"',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"JsonDecode","variable":match.group(1),"result":match.group(2)})

                # Basic assertion
                elif re.search(r'^Assert that\s+', instruction, re.IGNORECASE):
                    match = re.search(
                        r'Assert that\s+(.+?)\s+is equal to\s+(.+)$',
                        instruction, re.IGNORECASE
                    )
                    if match:
                        program["statements"].append({"type":"Assert","left":match.group(1).strip(),"right":match.group(2).strip()})

                # Boolean value of two variables
                elif re.search(r'^Set\s+"([^"]+)"\s+to the boolean value of\s+"([^"]+)"\s+and\s+"([^"]+)"', instruction, re.IGNORECASE):
                    match = re.search(r'^Set\s+"([^"]+)"\s+to the boolean value of\s+"([^"]+)"\s+and\s+"([^"]+)"', instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"BooleanOperation","operation":"and","left":match.group(2),"right":match.group(3),"result":match.group(1)})
                # Boolean OR value
                elif re.search(r'^Set\s+"([^"]+)"\s+to the boolean value of\s+"([^"]+)"\s+or\s+"([^"]+)"', instruction, re.IGNORECASE):
                    match = re.search(r'^Set\s+"([^"]+)"\s+to the boolean value of\s+"([^"]+)"\s+or\s+"([^"]+)"', instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"BooleanOperation","operation":"or","left":match.group(2),"right":match.group(3),"result":match.group(1)})
                # Boolean NOT value
                elif re.search(r'^Set\s+"([^"]+)"\s+to the opposite boolean value of\s+"([^"]+)"', instruction, re.IGNORECASE):
                    match = re.search(r'^Set\s+"([^"]+)"\s+to the opposite boolean value of\s+"([^"]+)"', instruction, re.IGNORECASE)
                    if match:
                        program["statements"].append({"type":"BooleanOperation","operation":"not","left":match.group(2),"result":match.group(1)})

                # Boolean AND
                elif (
                    "Perform AND operation" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Perform AND operation on\s+"([^"]+)"\s+and\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "BooleanOperation",
                            "operation": "and",
                            "left": match.group(1),
                            "right": match.group(2),
                            "result": match.group(3)
                        })

                # Boolean OR
                elif (
                    "Perform OR operation" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Perform OR operation on\s+"([^"]+)"\s+and\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "BooleanOperation",
                            "operation": "or",
                            "left": match.group(1),
                            "right": match.group(2),
                            "result": match.group(3)
                        })

                # Boolean NOT
                elif (
                    "Perform NOT operation" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Perform NOT operation on\s+"([^"]+)"\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "BooleanOperation",
                            "operation": "not",
                            "left": match.group(1),
                            "result": match.group(2)
                        })

                # Add
                elif (
                    "Add" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Add\s+(?:"([^"]+)"|(\S+))\s+and\s+(.+?)\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Add",
                            "left": match.group(1) if match.group(1) is not None else match.group(2),
                            "right": match.group(3).strip(),
                            "result": match.group(4)
                        })

                # Subtract
                elif (
                    "Subtract" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Subtract\s+"([^"]+)"\s+and\s+(.+?)\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Subtract",
                            "left": match.group(1),
                            "right": match.group(2).strip(),
                            "result": match.group(3)
                        })

                # Multiply
                elif (
                    "Multiply" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Multiply\s+"([^"]+)"\s+and\s+(.+?)\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Multiply",
                            "left": match.group(1),
                            "right": match.group(2).strip(),
                            "result": match.group(3)
                        })

                # Divide
                elif (
                    "Divide" in instruction
                    and "assign the result to" in instruction
                ):
                    match = re.search(
                        r'Divide\s+"([^"]+)"\s+and\s+(.+?)\s*,?\s*and\s+assign the result to\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Divide",
                            "left": match.group(1),
                            "right": match.group(2).strip(),
                            "result": match.group(3)
                        })

                # Otherwise If
                elif re.search(
                    r'^Otherwise If',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Otherwise If\s+"([^"]+)"\s+is\s+(greater than or equal to|less than or equal to|greater than|less than|equal to|not equal to)\s+(.+)',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ElseIf",
                            "variable": match.group(1),
                            "operator": match.group(2).lower(),
                            "value": match.group(3).strip()
                        })

                # If NOT
                elif re.search(
                    r'^If\s+NOT\s+',
                    instruction,
                    re.IGNORECASE
                ):
                    condition = re.sub(
                        r'^If\s+NOT\s+',
                        '',
                        instruction,
                        flags=re.IGNORECASE
                    )

                    program["statements"].append({
                        "type": "NotIf",
                        "condition": condition
                    })

                # Logical If
                elif re.search(
                    r'^If\s+',
                    instruction,
                    re.IGNORECASE
                ) and (
                    " AND " in instruction.upper()
                    or " OR " in instruction.upper()
                    or " NOT " in instruction.upper()
                ):
                    condition = re.sub(
                        r'^If\s+',
                        '',
                        instruction,
                        flags=re.IGNORECASE
                    )

                    program["statements"].append({
                        "type": "LogicalIf",
                        "condition": condition
                    })

                # Normal If
                elif re.search(
                    r'^If\s+',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'If\s+"([^"]+)"\s+is\s+(greater than or equal to|less than or equal to|greater than|less than|equal to|not equal to)\s+(.+)',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "If",
                            "variable": match.group(1),
                            "operator": match.group(2).lower(),
                            "value": match.group(3).strip()
                        })

                # Otherwise
                elif re.fullmatch(
                    r'Otherwise',
                    instruction,
                    re.IGNORECASE
                ):
                    program["statements"].append({
                        "type": "Else"
                    })

                # End If
                elif re.search(
                    r'End If',
                    instruction,
                    re.IGNORECASE
                ):
                    program["statements"].append({
                        "type": "EndIf"
                    })

                # Repeat
                elif re.search(
                    r'Repeat\s+(\d+)\s+times',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Repeat\s+(\d+)\s+times',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "Repeat",
                            "count": match.group(1)
                        })

                # End Repeat
                elif re.search(
                    r'End Repeat',
                    instruction,
                    re.IGNORECASE
                ):
                    program["statements"].append({
                        "type": "EndRepeat"
                    })

                # For Each
                elif re.search(
                    r'For each',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'For each\s+"([^"]+)"\s+in\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "ForEach",
                            "item": match.group(1),
                            "collection": match.group(2)
                        })

                # End For Each
                elif re.search(
                    r'End For Each',
                    instruction,
                    re.IGNORECASE
                ):
                    program["statements"].append({
                        "type": "EndForEach"
                    })

                # While
                elif re.search(
                    r'^While\s+',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'While\s+"([^"]+)"\s+is\s+(greater than or equal to|less than or equal to|greater than|less than|equal to|not equal to)\s+(.+)',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "While",
                            "variable": match.group(1),
                            "operator": match.group(2).lower(),
                            "value": match.group(3).strip()
                        })

                # End While
                elif re.search(
                    r'End While',
                    instruction,
                    re.IGNORECASE
                ):
                    program["statements"].append({
                        "type": "EndWhile"
                    })

                # Break
                elif re.fullmatch(
                    r'Break',
                    instruction,
                    re.IGNORECASE
                ):
                    program["statements"].append({
                        "type": "Break"
                    })

                # Continue
                elif re.fullmatch(
                    r'Continue',
                    instruction,
                    re.IGNORECASE
                ):
                    program["statements"].append({
                        "type": "Continue"
                    })

                # Display variable
                elif re.search(
                    r'Display the value of\s+"([^"]+)"',
                    instruction,
                    re.IGNORECASE
                ):
                    match = re.search(
                        r'Display the value of\s+"([^"]+)"',
                        instruction,
                        re.IGNORECASE
                    )

                    if match:
                        program["statements"].append({
                            "type": "DisplayVariable",
                            "variable": match.group(1)
                        })

            self.position += 1

        return program
