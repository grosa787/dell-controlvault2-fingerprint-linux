/* Exercise the real binary wrapper with only its hardware API interposed. */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>

static uint32_t device_status;
static unsigned int cancellations;
static unsigned char sample_ready;


uint32_t cv_fingerprint_update_enrollment(uint32_t handle, void *capture,
                                        uint32_t length, void *data,
                                        unsigned char *ready, void *token,
                                        uint32_t *extra)
{
    (void)handle; (void)capture; (void)length; (void)data;
    (void)token; (void)extra;
    if (device_status == 0)
        *ready = sample_ready;
    return device_status;
}

uint32_t cv_fingerprint_capture_cancel(void)
{
    cancellations++;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    void *fprint = dlopen("libfprint-2.so.2", RTLD_NOW | RTLD_GLOBAL);
    if (!fprint) { fprintf(stderr, "%s\n", dlerror()); return 2; }
    /* Like libfprint's module loader, leave unused vendor callbacks lazy. */
    void *library = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 2; }
    uint32_t *handle = dlsym(library, "cvhandle");
    uint32_t (*update)(void *, void *) =
        dlsym(library, "cvif_fingerprint_update_enrollment");
    if (!handle || !update) return 2;
    *handle = 1;
    const uint32_t input[] = {0x59, 0xa4, 0x89, 0x24, 0, 0};
    const uint32_t expected[] = {0x89, 0xa4, 0x89, 0x24, 0, 0x8f};
    const unsigned int expected_cancel[] = {0, 0, 0, 1, 0, 0};
    const unsigned char ready[] = {0, 0, 0, 0, 1, 0};
    for (unsigned int i = 0; i < sizeof(input) / sizeof(input[0]); i++) {
        unsigned char capture[20] = {1}, token[20] = {0};
        device_status = input[i];
        sample_ready = ready[i];
        cancellations = 0;
        uint32_t result = update(capture, token);
        if (result != expected[i] || cancellations != expected_cancel[i]) {
            fprintf(stderr, "status=0x%x: result=0x%x cancel=%u; expected=0x%x/%u\n",
                    input[i], result, cancellations, expected[i], expected_cancel[i]);
            return 1;
        }
    }
    dlclose(library);
    return 0;
}
