#ifndef Py_CPYTHON_PYFRAME_H
#  error "this header file must not be included directly"
#endif

PyAPI_DATA(PyTypeObject) PyFrame_Type;
PyAPI_DATA(PyTypeObject) PyFrameLocalsProxy_Type;

#define PyFrame_Check(op) Py_IS_TYPE((op), &PyFrame_Type)
#define PyFrameLocalsProxy_Check(op) Py_IS_TYPE((op), &PyFrameLocalsProxy_Type)

PyAPI_FUNC(PyFrameObject *) PyFrame_GetBack(PyFrameObject *frame);
PyAPI_FUNC(PyObject *) PyFrame_GetLocals(PyFrameObject *frame);

PyAPI_FUNC(PyObject *) PyFrame_GetGlobals(PyFrameObject *frame);
PyAPI_FUNC(PyObject *) PyFrame_GetBuiltins(PyFrameObject *frame);

PyAPI_FUNC(PyObject *) PyFrame_GetGenerator(PyFrameObject *frame);
PyAPI_FUNC(int) PyFrame_GetLasti(PyFrameObject *frame);
PyAPI_FUNC(PyObject*) PyFrame_GetVar(PyFrameObject *frame, PyObject *name);
PyAPI_FUNC(PyObject*) PyFrame_GetVarString(PyFrameObject *frame, const char *name);

/* The following functions are for use by debuggers and other tools
 * implementing custom frame evaluators with PEP 523. */

struct _PyInterpreterFrame;

/* Returns the code object of the frame (strong reference).
 * Does not raise an exception. */
PyAPI_FUNC(PyObject *) PyUnstable_InterpreterFrame_GetCode(struct _PyInterpreterFrame *frame);

/* Returns a byte offset into the last executed instruction.
 * Does not raise an exception. */
PyAPI_FUNC(int) PyUnstable_InterpreterFrame_GetLasti(struct _PyInterpreterFrame *frame);

/* Returns the currently executing line number, or -1 if there is no line number.
 * Does not raise an exception. */
PyAPI_FUNC(int) PyUnstable_InterpreterFrame_GetLine(struct _PyInterpreterFrame *frame);

/* Fills `out[0 .. co_nlocalsplus)` with the frame's local variables, indexed by
 * localsplus index, with cell and free variables unboxed to their contents.
 * Slots that are unset or hidden are set to NULL.  Free variables are read from
 * the function closure, so this works on a frame that has not started executing
 * (before COPY_FREE_VARS runs).  The frame is not modified.
 *
 * `out` must point to a buffer of at least co_nlocalsplus slots.
 *
 * On success returns co_nlocalsplus and each written slot holds a strong
 * reference (the caller must decref).  Returns -1 with an exception set if
 * `out` is NULL. */
PyAPI_FUNC(int) PyUnstable_InterpreterFrame_GetLocals(
    struct _PyInterpreterFrame *frame, PyObject **out);

#define PyUnstable_EXECUTABLE_KIND_SKIP 0
#define PyUnstable_EXECUTABLE_KIND_PY_FUNCTION 1
#define PyUnstable_EXECUTABLE_KIND_BUILTIN_FUNCTION 3
#define PyUnstable_EXECUTABLE_KIND_METHOD_DESCRIPTOR 4
#define PyUnstable_EXECUTABLE_KINDS 5

PyAPI_DATA(const PyTypeObject *) const PyUnstable_ExecutableKinds[PyUnstable_EXECUTABLE_KINDS+1];
