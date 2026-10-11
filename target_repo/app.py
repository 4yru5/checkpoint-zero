# TEST FIXTURE: deliberately unsafe. Only scanned as text, NEVER executed.
# Planted bug #1: eval() runs whatever the user types as Python code (code injection).


def calculate(user_input):
    return eval(user_input)
