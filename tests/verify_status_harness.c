#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>

static struct { uint32_t status, match; void *print; } result;
static int reports, reported_match, completions, retry_error;
static void *completion_error, *report_error;

unsigned long g_task_get_type(void) { return 0; }
void *g_type_check_instance_cast(void *instance, unsigned long type)
{ (void)type; return instance; }
void *g_task_get_task_data(void *task) { (void)task; return &result; }
void *fpi_device_retry_new(int code) { (void)code; return &retry_error; }
void fpi_device_verify_report(void *dev, int match, void *print, void *error)
{ (void)dev; (void)print; reports++; reported_match = match; report_error = error; }
void fpi_device_verify_complete(void *dev, void *error)
{ (void)dev; completions++; completion_error = error; }
void fpi_device_report_finger_status_changes(void *dev, unsigned int set, unsigned int clear)
{ (void)dev; (void)set; (void)clear; }

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
    *handle = 0; /* No USB close call on callback completion. */
    void (*callback)(void *, void *, void *) =
        (void *)((unsigned char *)info.dli_fbase + 0xd450);
    const uint32_t statuses[] = {0, 0, 0x89, 0x24};
    const uint32_t matches[] = {1, 0, 1, 1}; /* Include stale match on error. */
    for (unsigned int i = 0; i < 4; i++) {
        result.status = statuses[i]; result.match = matches[i]; result.print = NULL;
        reports = completions = 0; reported_match = -1; completion_error = report_error = NULL;
        callback(NULL, NULL, NULL);
        int retry = statuses[i] == 0x89;
        int expected_match = retry ? -1 : (statuses[i] == 0 && matches[i] == 1);
        if (completions != 1 || reports != 1 || completion_error != NULL ||
            reported_match != expected_match ||
            report_error != (retry ? &retry_error : NULL)) {
            fprintf(stderr, "status=0x%x match=%u reports=%d result=%d completions=%d retry=%d\n",
                    statuses[i], matches[i], reports, reported_match, completions,
                    completion_error == &retry_error);
            return 1;
        }
    }
    dlclose(library);
    return 0;
}
