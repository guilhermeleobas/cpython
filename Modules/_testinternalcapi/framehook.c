#include "parts.h"
#include "pycore_interpframe.h"


static int counter = 0;

int
ignore_frame(_PyInterpreterFrame *frame, PyCodeObject *code)
{
    if ((_PyFrame_IsIncomplete(frame)) ||
        (frame->owner != FRAME_OWNED_BY_THREAD) ||
        (code->co_flags & CO_GENERATOR) ||
        (code->co_flags & CO_COROUTINE) ||
        (code->co_flags & CO_ASYNC_GENERATOR)) {
        return 1;
    }
    if ((PyUnicode_CompareWithASCIIString(code->co_name, "<lambda>") == 0) ||
        (PyUnicode_CompareWithASCIIString(code->co_name, "__exit__") == 0)) {
        return 1;
    }
    return 0;
}


static PyCodeObject*
dummy_frame_hook(_PyInterpreterFrame *frame)
{
    PyCodeObject *code = (PyCodeObject *)PyUnstable_InterpreterFrame_GetCode(frame);
    if (ignore_frame(frame, code)) {
        Py_INCREF(code);
        return code;
    }

    counter += 1;

    PyObject *new_code = PyObject_CallMethod((PyObject *)code, "replace", NULL);
    Py_INCREF(new_code);
    return (PyCodeObject *)new_code;
}



struct Hooks {
    const char* name;
    _PyFrameHookFunction function;
    PyObject *wrapped;  // cached PyCapsule for add/remove
};


static struct Hooks available_hooks[] = {
    {"dummy_frame_hook", dummy_frame_hook, NULL},
    {NULL, NULL, NULL}
};


static PyObject*
add_hook(PyObject* self, PyObject* arg)
{
    PyInterpreterState *interp = PyInterpreterState_Get();
    const char* name = PyUnicode_AsUTF8(arg);

    for (int i = 0; available_hooks[i].name != NULL; i++) {
        if (strcmp(name, available_hooks[i].name) == 0) {
            if (PyUnstable_AddFrameHook(interp, available_hooks[i].wrapped) < 0) {
                PyErr_SetString(PyExc_RuntimeError, "Failed to add frame hook");
                return NULL;
            }
            Py_RETURN_NONE;
        }
    }

    PyErr_SetString(PyExc_RuntimeError, "Failed to add frame hook");
    return NULL;
}


static PyObject*
remove_hook(PyObject* self, PyObject* arg)
{
    PyInterpreterState *interp = PyInterpreterState_Get();
    const char* name = PyUnicode_AsUTF8(arg);

    for (int i = 0; available_hooks[i].name != NULL; i++) {
        if (strcmp(name, available_hooks[i].name) == 0) {
            if (PyUnstable_RemoveFrameHook(interp, available_hooks[i].wrapped) < 0) {
                PyErr_SetString(PyExc_RuntimeError, "Failed to remove frame hook");
                return NULL;
            }
            Py_RETURN_NONE;
        }
    }

    PyErr_SetString(PyExc_RuntimeError, "Unknown frame hook name");
    return NULL;
}


static PyObject*
get_counter(PyObject* self, PyObject* Py_UNUSED(ignored))
{
    return PyLong_FromLong(counter);
}

static PyObject*
reset_counter(PyObject* self, PyObject* Py_UNUSED(ignored))
{
    counter = 0;
    Py_RETURN_NONE;
}


static PyMethodDef test_methods[] = {
    {"add_hook", add_hook, METH_O, NULL},
    {"get_counter", get_counter, METH_NOARGS, NULL},
    {"remove_hook", remove_hook, METH_O, NULL},
    {"reset_counter", reset_counter, METH_NOARGS, NULL},
    {NULL},
};

int
_PyTestInternalCapi_Init_FrameHook(PyObject *m)
{
    for (int i = 0; available_hooks[i].name != NULL; i++) {
        available_hooks[i].wrapped =
            PyUnstable_WrapFrameHookFunction(available_hooks[i].function);
        if (available_hooks[i].wrapped == NULL) {
            return -1;
        }
    }
    return PyModule_AddFunctions(m, test_methods);
}