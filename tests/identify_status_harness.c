/* Execute the real identify callback; device and libfprint calls are intercepted. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>

/* Task result layout recovered from the pinned driver. */
static struct { uint32_t status, match; void *print; } result;
static int reports, completions, retries, closes, bad_call, retry_error;
static int fake_print, fake_device;
static void *reported_match, *reported_print, *report_error, *completion_error;

unsigned long g_task_get_type(void) { return 0; }
void *g_type_check_instance_cast(void *instance, unsigned long type)
{ (void)type; return instance; }
void *g_task_get_task_data(void *task) { (void)task; return &result; }
void *fpi_device_retry_new(int code)
{
    retries++;
    if (code != 0) bad_call = 1;
    return &retry_error;
}
void fpi_device_identify_report(void *dev, void *match, void *print, void *error)
{
    if (dev != &fake_device || completions) bad_call = 1;
    reports++; reported_match = match; reported_print = print; report_error = error;
}
void fpi_device_identify_complete(void *dev, void *error)
{
    if (dev != &fake_device || reports != 1) bad_call = 1;
    completions++; completion_error = error;
}
uint32_t cv_close_partial(uint32_t handle, uint32_t flags)
{
    if (handle != 42 || flags != 1 || completions != 1) bad_call = 1;
    closes++;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    if (!dlopen("libfprint-2.so.2", RTLD_NOW | RTLD_GLOBAL)) return 2;
    void *library = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 2; }
    void *symbol = dlsym(library, "cvif_fingerprint_identify");
    Dl_info info;
    if (!symbol || !dladdr(symbol, &info)) return 2;
    uint32_t *handle = dlsym(library, "cvhandle");
    if (!handle) return 2;
    /* The callback is not exported; its offset is specific to the pinned ELF. */
    void (*callback)(void *, void *, void *) =
        (void *)((unsigned char *)info.dli_fbase + 0xd370);
    const uint32_t statuses[] = {0, 0x89, 0x24, 0x59};
    for (unsigned i = 0; i < sizeof(statuses) / sizeof(statuses[0]); i++) {
        for (unsigned match = 0; match <= 1; match++) {
            for (unsigned session = 0; session <= 1; session++) {
                result.status = statuses[i]; result.match = match;
                result.print = &fake_print; /* Deliberately stale on error/no match. */
                *handle = session ? 42 : 0;
                reports = completions = retries = closes = bad_call = 0;
                reported_match = reported_print = report_error = completion_error = NULL;
                callback(&fake_device, NULL, NULL);
                int retry = statuses[i] == 0x89;
                void *expected_match = statuses[i] == 0 && match ? &fake_print : NULL;
                if (bad_call || reports != 1 || completions != 1 || retries != retry ||
                    closes != (int)session || *handle != 0 || completion_error ||
                    reported_match != expected_match || reported_print ||
                    report_error != (retry ? &retry_error : NULL)) {
                    fprintf(stderr, "status=0x%x match=%u session=%u: reports=%d completions=%d retries=%d closes=%d bad=%d\n",
                            statuses[i], match, session, reports, completions, retries, closes, bad_call);
                    return 1;
                }
            }
        }
    }
    dlclose(library);
    return 0;
}
