#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
/* Synthetic object ID: only argument forwarding is under test. */
static const uint32_t object_id = 0x12345678;
static unsigned calls;
static uint32_t response;
static int bad_args;
uint32_t cv_delete_object(uint32_t session, uint32_t object, uint32_t length,
                          const unsigned char *auth, void *callback, void *context)
{
    static const unsigned char expected[] = {
        1,1,0xff,0,0,0,13,0,12,'B','r','o','a','d','c','o','m','W','B','F',0
    };
    calls++;
    if (session != 42 || object != object_id || length != sizeof(expected) ||
        !auth || memcmp(auth, expected, sizeof(expected)) || callback || context)
        bad_args = 1;
    return response;
}
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    if (!dlopen("libfprint-2.so.2", RTLD_NOW | RTLD_GLOBAL)) return 2;
    void *library = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 2; }
    uint32_t *handle = dlsym(library, "cvhandle");
    uint32_t (*delete)(uint32_t) = dlsym(library, "cvif_fingerprint_delete");
    if (!handle || !delete) return 2;
    *handle = 42;
    const uint32_t statuses[] = {0, 8, 27};
    for (unsigned i = 0; i < 3; i++) {
        response = statuses[i]; calls = 0; bad_args = 0;
        if (delete(object_id) != response || calls != 1 || bad_args) return 1;
    }
    *handle = 0; calls = 0;
    if (delete(object_id) != 6 || calls) return 1;
    return 0;
}
