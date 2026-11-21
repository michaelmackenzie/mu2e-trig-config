# Compare two trigger reports

import sys
from math import sqrt

# Should run in every event, previous was ProcessCFOData/EWMProducer
TIMING_REF_MODULE = "LumiStreamPS"


# --------------------------------------------------------------
# Fill the log results
def fill_results(f, verbose=0):
    results = {}

    timing_info = []
    reference_timing_info = []
    first_event_time = -1.0
    nevents = -1
    for line in f:
        if verbose > 1:
            print(line)
        # Exit once the trigger path summary has completed
        if "End-path summary" in line:
            break
        words = line.split()
        # Check if the database initialization time is given
        if "DbEngine inclusive beginJob time was" in line:
            first_event_time = float(words[-2])
        # Check if it's the timing information for the full event processing
        if len(words) == 8 and words[0] == "Full" and words[1] == "event":
            #             [min, avg, max, median, rms]
            timing_info = [float(words[index]) for index in range(2, 7)]
            nevents = int(words[-1])
            if verbose > 0:
                print(
                    "Timing info:    min        avg        max       median     rms    nevents"
                )
                print(
                    "             %.3e  %.3e  %.3e  %.3e  %.3e %i"
                    % (
                        timing_info[0],
                        timing_info[1],
                        timing_info[2],
                        timing_info[3],
                        timing_info[3],
                        nevents,
                    )
                )
            continue
        # Check if it's the reference module for node timing
        is_ref = len(words) == 7 and TIMING_REF_MODULE in words[0]
        if is_ref and len(reference_timing_info) == 0:
            #             [min, avg, max, median, rms]
            reference_timing_info = [float(words[index]) for index in range(1, 6)]
            if verbose > 0:
                print("Timing info:    min        avg        max       median     rms")
                print(
                    "             %.3e  %.3e  %.3e  %.3e  %.3e"
                    % (
                        reference_timing_info[0],
                        reference_timing_info[1],
                        reference_timing_info[2],
                        reference_timing_info[3],
                        reference_timing_info[3],
                    )
                )
                print("Path                          :    run   pass   fail  error")
            continue
        # Check if it's a trigger path summary line
        if len(words) != 7 or words[0] != "TrigReport":
            continue
        try:
            #        [run, pass, fail, error]
            counts = [int(words[index]) for index in range(2, 6)]
            path = words[-1]
            results[path] = counts
            if verbose > 0:
                print(
                    "%30s: %6i %6i %6i %6i"
                    % (path, counts[0], counts[1], counts[2], counts[3])
                )
        except:
            continue

    # Adjust the processing times to remove the database access time
    if first_event_time > 0 and nevents > 0:
        print("First event processing time: %.4f" % (first_event_time))
        time_shift = first_event_time / nevents
        print(
            "--> Adjusting the average time by %.5f: %.5f --> %.5f"
            % (time_shift, timing_info[1], timing_info[1] - time_shift)
        )
        timing_info[1] -= time_shift
    return results, timing_info, reference_timing_info


# --------------------------------------------------------------
# Main execution
if len(sys.argv) < 3:
    print(
        "Not enough arguments! Useage: python check_trigger_results.py <file_1> <file_2> [verbose level, default = 0]"
    )
    exit(2)
verbose = int(sys.argv[3]) if len(sys.argv) == 4 else 0

file_1 = sys.argv[1]  # Local log file
file_2 = sys.argv[2]  # Reference log file
try:
    f_1 = open(file_1, "r")
    f_2 = open(file_2, "r")
except FileNotFoundError:
    print("Files were not both found!")
    exit(2)

if verbose > 0:
    print(">>> Retrieving info from the local processing")
results_1, timing_1, reference_time_1 = fill_results(f_1, verbose)
if verbose > 0:
    print(">>> Retrieving info from the reference processing")
results_2, timing_2, reference_time_2 = fill_results(f_2, verbose)

# Define the major vs. minor failure thresholds
count_minor_threshold = 1  # path rate change for minor failure
count_major_threshold = 1.5  # path rate change sigma for major failure
avg_time_minor_threshold = 0.40  # fractional change in time / event
avg_time_major_threshold = 0.50  # fractional change in time / event
minor_fail = False
major_fail = False

# Check the path rates
for path in results_1:
    if path in results_2:
        counts_1 = results_1[path]
        counts_2 = results_2[path]
        for index in range(len(counts_1)):
            delta = abs(counts_1[index] - counts_2[index])
            sigma = (
                sqrt(counts_2[index])
                if counts_2[index] > 0
                else 2 / count_major_threshold
            )  # default to 2 events if none before
            z = delta / sigma
            if z >= count_major_threshold:
                major_fail = True
                print(">>> Path " + path + " has a major change!")
                print("Local counts    :", counts_1)
                print(
                    "Reference counts:",
                    counts_2,
                    "(delta/sqrt(reference) = %.2f)" % (z),
                )
                break
            elif delta >= count_minor_threshold:
                minor_fail = True
                print(">>> Path " + path + " has a minor change:")
                print("Local counts    :", counts_1)
                print(
                    "Reference counts:",
                    counts_2,
                    "(delta/sqrt(reference) = %.2f)" % (z),
                )
                break
    else:
        print(">>> New trigger path " + path + " in local found, not in the reference!")
        major_fail = True
for path in results_2:
    if path not in results_1:
        print(">>> Trigger path " + path + " in reference not found in local!")
        major_fail = True


if len(timing_1) == 0 or len(reference_time_1) == 0:
    print(">>> Failed to retrieve the timing information for the new processing!")
    major_fail = True
elif len(timing_2) == 0 or len(reference_time_2) == 0:
    print(">>> Failed to retrieve the timing information for the reference processing!")
    major_fail = True
else:
    # Check the timing rates
    time_scale = reference_time_2[1] / reference_time_1[1]
    scaled_time = timing_1[1] * time_scale
    avg_time_delta = abs(scaled_time / timing_2[1] - 1.0)
    print(
        "Evaluating a timing scale: %.3e (new) and %.3e (reference) --> scale = %.2f"
        % (reference_time_1[1], reference_time_2[1], time_scale)
    )
    print(
        "Total processing time per event: %.4f (new) (%.4f scaled) vs. %.4f (reference), |time_new / time_ref - 1| = %.3f"
        % (timing_1[1], scaled_time, timing_2[1], avg_time_delta)
    )
    if avg_time_delta > avg_time_major_threshold:
        print(
            ">>> Average time changed significantly: %.4f (new) vs. %.4f (reference) given a time scale of %.2f to the new time (%.3e)"
            % (timing_1[1], timing_2[1], time_scale, scaled_time)
        )
        major_fail = True
    elif avg_time_delta > avg_time_minor_threshold:
        print(
            ">>> Average time changed somewhat significantly: %.4f (new) vs. %.4f (reference) given a time scale of %.2f to the new time (%.3e)"
            % (timing_1[1], timing_2[1], time_scale, scaled_time)
        )
        minor_fail = True

# Return the exit codes for minor/major failures
if major_fail:
    exit(2)
if minor_fail:
    exit(1)

# No failures
print("No problems detected")
exit(0)
