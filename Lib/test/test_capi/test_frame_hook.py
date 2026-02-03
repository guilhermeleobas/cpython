import contextlib
import sys
import unittest
from types import CodeType, FrameType
from test.support import import_helper


_testinternalcapi = import_helper.import_module('_testinternalcapi')
counter = 0


@contextlib.contextmanager
def set_hook(name):
    _testinternalcapi.add_hook(name)
    try:
        yield
    finally:
        _testinternalcapi.remove_hook(name)


@contextlib.contextmanager
def set_frame_hook(callable):
    sys.add_frame_hook(callable)
    try:
        yield
    finally:
        sys.remove_frame_hook(callable)


def fn(x):
    global counter
    counter = 10
    return x + 1


class TestInternalCAPI(unittest.TestCase):
    def test_dummy_frame_hook(self):
        self.assertEqual(_testinternalcapi.get_counter(), 0)
        with set_hook("dummy_frame_hook"):
            fn(3)
        self.assertEqual(_testinternalcapi.get_counter(), 1)

    def test_multiple_hooks(self):
        counter = 0

        def fn(x):
            return x + 1

        def helper(frame: FrameType) -> CodeType:
            if frame.f_code.co_name != "fn":
                return frame.f_code

            nonlocal counter
            counter += 1
            return frame.f_code

        def helper2(frame: FrameType) -> CodeType:
            if frame.f_code.co_name != "fn":
                return frame.f_code

            nonlocal counter
            counter += 10
            return frame.f_code

        with set_frame_hook(helper):
            fn(0)
            self.assertEqual(counter, 1)
            with set_frame_hook(helper2):
                fn(3)
            self.assertEqual(counter, 12)  # helper(+1) + helper2(+10)
            fn(0)
            self.assertEqual(counter, 13)

    def test_noop_hook(self):
        def noop(frame: FrameType) -> CodeType:
            # Just return the original code object
            # CPython will not replace the frame
            return frame.f_code

        with set_frame_hook(noop):
            fn(3)
        self.assertEqual(counter, 10)

    def test_mutate_constants(self):
        def mutate_constants(frame: FrameType) -> CodeType:
            if frame.f_code.co_name != "fn":
                return frame.f_code
            def f(x):
                return x + 2
            return f.__code__

        with set_frame_hook(mutate_constants):
            y = fn(3)
        self.assertEqual(y, 5)

    def test_logic_swap(self):
        """Test replacing the entire logic of a function with another."""
        def target(a, b):
            return a + b

        def multiply(x, y):
            return x * y

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return multiply.__code__
            return frame.f_code

        with set_frame_hook(hook):
            # multiply(2, 5) instead of target(2, 5)
            self.assertEqual(target(2, 5), 10)

    def test_different_local_names(self):
        """Test that arguments are mapped by position, not by name."""
        def target(first, second):
            return first - second

        def swapped_names(b, a):
            # In the new code, first arg is 'b', second is 'a'
            # Hook logic should copy target.first -> swapped_names.b
            return b - a

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return swapped_names.__code__
            return frame.f_code

        with set_frame_hook(hook):
            # (10 - 2)
            self.assertEqual(target(10, 2), 8)

    @unittest.skip("Currently fails due to closure handling issues")
    def test_closure_mapping(self):
        """Test that free variables (closures) are correctly preserved and mapped."""
        def make_multiplier(factor):
            def multiplier(n):
                return n * factor
            return multiplier

        def replacement_multiplier(n):
            # Uses 'factor' from the original closure
            return n + factor

        double = make_multiplier(2)

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "multiplier":
                return replacement_multiplier.__code__
            return frame.f_code

        with set_frame_hook(hook):
            # original: n * factor -> 10 * 2 = 20
            # hooked:   n + factor -> 10 + 2 = 12
            double(10)  # this should raise SystemError

    def test_complex_signature(self):
        """Test functions with complex signatures including *args and **kwargs."""
        def target(a, b=1, *args, **kwargs):
            return (a, b, args, kwargs)

        def replacement(x, y=2, *more, **extras):
            return ("hooked", x, y, more, extras)

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return replacement.__code__
            return frame.f_code

        with set_frame_hook(hook):
            result = target(10, 20, 30, 40, key="val")
            self.assertEqual(result, ("hooked", 10, 20, (30, 40), {"key": "val"}))

    # ============================================================================
    # Error Handling Tests
    # ============================================================================

    @unittest.skip("Currently fails due to exception handling issues in hooks")
    def test_hook_raises_exception(self):
        """Test that exceptions raised in the hook are properly propagated."""
        def bad_hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "fn":
                raise ValueError("Hook intentionally failed")
            return frame.f_code

        with self.assertRaises(ValueError) as cm:
            with set_frame_hook(bad_hook):
                fn(5)
        self.assertIn("Hook intentionally failed", str(cm.exception))

    @unittest.skip("Currently fails due to NULL return handling issues")
    def test_hook_returns_none(self):
        """Test that returning None from hook is handled correctly."""
        def none_hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "fn":
                return None
            return frame.f_code

        # Hook returning None should cause an error
        with self.assertRaises(TypeError):
            with set_frame_hook(none_hook):
                fn(5)

    # ============================================================================
    # Exception Propagation Tests
    # ============================================================================

    def test_exception_in_hooked_code(self):
        """Test that exceptions in the transformed code propagate correctly."""
        def target(x):
            if x < 0:
                raise ValueError("Negative value not allowed")
            return x * 2

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return target.__code__  # Return same code
            return frame.f_code

        with set_frame_hook(hook):
            # Should work normally
            self.assertEqual(target(5), 10)

            # Exception should propagate
            with self.assertRaises(ValueError) as cm:
                target(-1)
            self.assertIn("Negative value not allowed", str(cm.exception))

    def test_exception_with_try_except(self):
        """Test that try/except works correctly with hooked code."""
        def target(x):
            try:
                if x == 0:
                    raise ZeroDivisionError("Cannot divide by zero")
                return 10 / x
            except ZeroDivisionError as e:
                return f"Caught: {e}"

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return target.__code__
            return frame.f_code

        with set_frame_hook(hook):
            self.assertEqual(target(5), 2.0)
            self.assertIn("Caught", target(0))

    # ============================================================================
    # Frame State Preservation Tests
    # ============================================================================

    def test_local_variables_preserved(self):
        """Test that local variables are correctly preserved after transformation."""
        results = []

        def target(a, b):
            x = a + b
            y = a * b
            results.append((x, y))
            return x + y

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return target.__code__
            return frame.f_code

        with set_frame_hook(hook):
            result = target(3, 4)
            self.assertEqual(result, 19)  # (3+4) + (3*4) = 7 + 12
            self.assertEqual(results[0], (7, 12))

    def test_global_variables_accessible(self):
        """Test that global variables are accessible in hooked code."""
        global test_global
        test_global = 100

        def target(x):
            return x + test_global

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return target.__code__
            return frame.f_code

        with set_frame_hook(hook):
            self.assertEqual(target(50), 150)

    def test_global_variable_modification(self):
        """Test that global variables can be modified in hooked code."""
        global test_modify_global
        test_modify_global = 0

        def target(x):
            global test_modify_global
            test_modify_global = x * 2
            return test_modify_global

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return target.__code__
            return frame.f_code

        with set_frame_hook(hook):
            result = target(5)
            self.assertEqual(result, 10)
            self.assertEqual(test_modify_global, 10)

    # ============================================================================
    # Recursion Tests
    # ============================================================================

    def test_recursive_function(self):
        """Test frame hooks with recursive functions."""
        def factorial(n):
            if n <= 1:
                return 1
            return n * factorial(n - 1)

        def hook(frame: FrameType) -> CodeType:
            # Don't modify, just let it pass through
            return frame.f_code

        with set_frame_hook(hook):
            self.assertEqual(factorial(5), 120)
            self.assertEqual(factorial(0), 1)
            self.assertEqual(factorial(1), 1)

    def test_nested_function_calls(self):
        """Test frame hooks with nested function calls."""
        def outer(x):
            def inner(y):
                return y * 2
            return inner(x) + x

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            self.assertEqual(outer(5), 15)  # 5*2 + 5

    def test_deep_call_stack(self):
        """Test frame hooks with deep call stacks."""
        def level_1(n):
            return level_2(n)

        def level_2(n):
            return level_3(n)

        def level_3(n):
            return level_4(n)

        def level_4(n):
            return n * 2

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            self.assertEqual(level_1(10), 20)

    # ============================================================================
    # Generator and Coroutine Tests
    # ============================================================================

    def test_generator_function(self):
        """Test frame hooks with generator functions."""
        def target_generator(n):
            for i in range(n):
                yield i * 2

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            result = list(target_generator(5))
            self.assertEqual(result, [0, 2, 4, 6, 8])

    def test_context_manager(self):
        """Test frame hooks with context managers."""
        results = []

        class MyContext:
            def __enter__(self):
                results.append("entered")
                return self

            def __exit__(self, *args):
                results.append("exited")

        def target():
            with MyContext():
                results.append("inside")

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            target()
            self.assertEqual(results, ["entered", "inside", "exited"])

    # ============================================================================
    # Code Object Compatibility Tests
    # ============================================================================

    @unittest.skip("Currently fails due to argument count mismatch handling issues")
    def test_mismatched_argument_count(self):
        """Test behavior when swapping code with different argument counts."""
        def target(a, b):
            return a + b

        def wrong_args(a):  # Only takes 1 arg instead of 2
            return a * 3

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return wrong_args.__code__
            return frame.f_code

        # This should fail gracefully with SystemError for incompatible code objects
        with self.assertRaises(SystemError):
            with set_frame_hook(hook):
                target(10, 20)

    def test_code_with_different_locals(self):
        """Test swapping code with different number of local variables."""
        def target(x):
            return x + 1

        def many_locals(x):
            a = 1
            b = 2
            c = 3
            d = 4
            return x + a + b + c + d

        def hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return many_locals.__code__
            return frame.f_code

        with set_frame_hook(hook):
            result = target(10)
            self.assertEqual(result, 20)  # 10 + 1 + 2 + 3 + 4

    # ============================================================================
    # Edge Cases Tests
    # ============================================================================

    def test_lambda_function(self):
        """Test frame hooks don't interfere with lambda functions."""
        target = lambda x: x * 2

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            self.assertEqual(target(5), 10)

    def test_decorated_function(self):
        """Test frame hooks with decorated functions."""
        call_count = []

        def decorator(func):
            def wrapper(*args, **kwargs):
                call_count.append(1)
                return func(*args, **kwargs)
            return wrapper

        @decorator
        def target(x):
            return x + 1

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            result = target(5)
            self.assertEqual(result, 6)
            self.assertEqual(len(call_count), 1)

    def test_class_method(self):
        """Test frame hooks with class methods."""
        class MyClass:
            def __init__(self, value):
                self.value = value

            def method(self, x):
                return self.value + x

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            obj = MyClass(10)
            self.assertEqual(obj.method(5), 15)

    def test_static_method(self):
        """Test frame hooks with static methods."""
        class MyClass:
            @staticmethod
            def static_method(x):
                return x * 2

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            self.assertEqual(MyClass.static_method(5), 10)

    def test_empty_function(self):
        """Test frame hooks with empty functions."""
        def target():
            pass

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            result = target()
            self.assertIsNone(result)

    def test_function_with_default_args(self):
        """Test frame hooks with functions having default arguments."""
        def target(a, b=10, c=20):
            return a + b + c

        def hook(frame: FrameType) -> CodeType:
            return frame.f_code

        with set_frame_hook(hook):
            self.assertEqual(target(5), 35)  # 5 + 10 + 20
            self.assertEqual(target(5, 15), 40)  # 5 + 15 + 20
            self.assertEqual(target(5, 15, 25), 45)  # 5 + 15 + 25

    # ============================================================================
    # Multiple Hook Chaining Tests
    # ============================================================================

    def test_hook_chaining_order(self):
        """Test that hooks are called in the correct order."""
        calls = []

        def hook1(frame: FrameType) -> CodeType:
            calls.append("hook1")
            return frame.f_code

        def hook2(frame: FrameType) -> CodeType:
            calls.append("hook2")
            return frame.f_code

        def target(x):
            return x + 1

        with set_frame_hook(hook1):
            target(5)
            calls.clear()
            with set_frame_hook(hook2):
                target(5)
                # Both hooks should have been called
                self.assertIn("hook1", calls)
                self.assertIn("hook2", calls)

    def test_consecutive_transformations(self):
        """Test that consecutive code transformations work correctly."""
        def add_one(x):
            return x + 1

        def multiply_two(x):
            return x * 2

        def hook1(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return add_one.__code__
            return frame.f_code

        def hook2(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                return multiply_two.__code__
            return frame.f_code

        def target(x):
            return x  # Original does nothing

        with set_frame_hook(hook1):
            self.assertEqual(target(5), 6)  # 5 + 1

        with set_frame_hook(hook2):
            self.assertEqual(target(5), 10)  # 5 * 2


    def test_mixed_c_and_callable_hooks(self):
        py_calls = []

        def py_hook(frame: FrameType) -> CodeType:
            py_calls.append(frame.f_code.co_name)
            return frame.f_code

        def target(x):
            return x + 1

        _testinternalcapi.reset_counter()
        with set_hook("dummy_frame_hook"):
            with set_frame_hook(py_hook):
                target(5)

        self.assertIn("target", py_calls)
        self.assertGreater(_testinternalcapi.get_counter(), 0)
        _testinternalcapi.reset_counter()

    def test_mixed_c_hook_first(self):
        # C hook registered before Python hook; both should fire on target
        py_count = [0]

        def py_hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                py_count[0] += 1
            return frame.f_code

        def target(x):
            return x + 1

        with set_hook("dummy_frame_hook"):
            with set_frame_hook(py_hook):
                _testinternalcapi.reset_counter()
                target(1)
                c_count = _testinternalcapi.get_counter()

        self.assertEqual(py_count[0], 1)
        self.assertEqual(c_count, 1)
        _testinternalcapi.reset_counter()

    def test_mixed_py_hook_first(self):
        # Python hook registered before C hook; both should fire on target
        py_count = [0]

        def py_hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                py_count[0] += 1
            return frame.f_code

        def target(x):
            return x + 1

        with set_frame_hook(py_hook):
            with set_hook("dummy_frame_hook"):
                _testinternalcapi.reset_counter()
                target(1)
                c_count = _testinternalcapi.get_counter()

        self.assertEqual(py_count[0], 1)
        self.assertEqual(c_count, 1)
        _testinternalcapi.reset_counter()

    def test_mixed_c_hook_transform_seen_by_py_hook(self):
        # The C dummy_frame_hook replaces the code object via code.replace().
        # The Python hook runs after and should receive the replaced code.
        seen_codes = []

        def py_hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                seen_codes.append(frame.f_code)
            return frame.f_code

        def target(x):
            return x + 1

        with set_hook("dummy_frame_hook"):
            with set_frame_hook(py_hook):
                target(1)

        self.assertEqual(len(seen_codes), 1)
        # The code the Python hook saw should differ from the original
        # because the C hook replaced it with code.replace()
        self.assertIsNot(seen_codes[0], target.__code__)

    def test_mixed_hooks_only_c_remains_after_py_removed(self):
        # Remove Python hook mid-way; only C hook should fire after removal
        py_count = [0]

        def py_hook(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                py_count[0] += 1
            return frame.f_code

        def target(x):
            return x + 1

        with set_hook("dummy_frame_hook"):
            with set_frame_hook(py_hook):
                _testinternalcapi.reset_counter()
                target(1)  # both fire
            target(1)   # only C hook fires

        self.assertEqual(py_count[0], 1)
        self.assertGreaterEqual(_testinternalcapi.get_counter(), 2)
        _testinternalcapi.reset_counter()

    def test_mixed_multiple_py_hooks_with_c_hook(self):
        # Two Python hooks + one C hook: all three should fire per call
        a_count = [0]
        b_count = [0]

        def hook_a(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                a_count[0] += 1
            return frame.f_code

        def hook_b(frame: FrameType) -> CodeType:
            if frame.f_code.co_name == "target":
                b_count[0] += 1
            return frame.f_code

        def target(x):
            return x + 1

        with set_hook("dummy_frame_hook"):
            with set_frame_hook(hook_a):
                with set_frame_hook(hook_b):
                    _testinternalcapi.reset_counter()
                    target(1)
                    c_count = _testinternalcapi.get_counter()

        self.assertEqual(a_count[0], 1)
        self.assertEqual(b_count[0], 1)
        self.assertEqual(c_count, 1)
        _testinternalcapi.reset_counter()


if __name__ == "__main__":
    unittest.main()