class Lexer:
    def __init__(self, source_code):
        self.source_code = source_code
        self.tokens = []

    def tokenize(self):
        lines = self.source_code.splitlines()

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()

            if not line:
                continue

            if line == "START":
                self.tokens.append(("START", line_number))

            elif line == "END":
                self.tokens.append(("END", line_number))

            elif line.startswith("Step"):
                self.tokens.append(("STEP", line_number, line))

            else:
                self.tokens.append(("UNKNOWN", line_number, line))

        return self.tokens