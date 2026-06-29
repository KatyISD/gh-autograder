import json
import os
import subprocess
import sys
import yaml



def normalize_tests(tests):
    """
    Normalize the tests so that the other methods can work with it. The
    file may be either a legacy yaml file used with GitHub actions or
    formatted just for tests. This takes the legacy format and converts
    to the new format. 
    """

    # Check if test has jobs.run-autograding-tests, if so, legacy
    if (tests.get("jobs", {}).get("run-autograding-tests") is  not None):
        test_list = tests["jobs"]["run-autograding-tests"]["steps"]
        new_test_list = []
        for t in test_list:
            uses = t.get("uses")
            if "autograding-io-grader" in uses or "autograding-junit4" in uses:
                new_with = t.get("with", {})
                new_test = {
                    "comparison": new_with.get("comparison-method", "exact"),
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "points": new_with.get("max-score", 0),                     
                    "timeout": (new_with.get("timeout", 0) * 60), # Legacy is in minutes, new is in seconds
                    "loose": {
                        "trim": new_with.get("loose-trim", False),
                        "rtrim": new_with.get("loose-rtrim", True),
                        "ltrim": new_with.get("loose-ltrim", False),
                        "ignore-blank": new_with.get("loose-ignore-blank-lines", True),
                        "squash-spaces": new_with.get("loose-squash-spaces", True),
                    },
                    "output": new_with.get("expected-output", ""),
                    "input": new_with.get("input", ""),
                    "filename": new_with.get("filename", ""),
                    "input-file": new_with.get("input-file", ""),
                    "output-file": new_with.get("output-file", ""),
                    "command": new_with.get("command", ""),
                    "setup": new_with.get("setup-command", ""),
                    "regex": new_with.get("regex", ""),
                }

                if ("autograding-io-grader" in uses):
                    new_test["type"] = "io"
                elif ("autograding-junit4" in uses):
                    new_test["type"] = "junit4"
                

                new_test_list.append(new_test)
        tests = {
            "tests": new_test_list,
        }
    return tests

def load_io(tests):
    """
    If there are files set for input and output, load them into
    the dictionary. This will override anything that's already
    there.
    """
    
    for t in tests.get("tests", []):
        if t.get("input-file"):
            with open(t["input-file"], 'r') as f:
                t["input"] = f.read()
        if t.get("output-file"):
            with open(t["output-file"], 'r') as f:
                t["output"] = f.read()
    return tests

def main(): 
    # Check if tests.yaml or tests.yml exists in the current directory
    if os.path.exists('tests.yaml'):
        with open('tests.yaml', 'r') as file:
            tests = yaml.safe_load(file)
    elif os.path.exists('tests.yml'):
        with open('tests.yml', 'r') as file:
            tests = yaml.safe_load(file)
    else:
        # Just exit, it'll be a no test run
        sys.exit(0)

    tests = normalize_tests(tests)
    tests = load_io(tests)

    status = {
        "points": 0,
        "points_available": 0,
        "tests_run": 0,
    }

    # Iterate through tests and run the individual tests
    for t in tests.get('tests', []):
        status["tests_run"] += 1
        status["points_available"] += t.get("points", 0)

        if t.get("type") == "io":
            result = test_io(t)
            print(json.dumps(result, indent=4))

        




def test_io(test):
    """
    Runs an individual IO test and returns dictionary with the results
    """

    # Set defaults
    ret = {
        "setup": {
            "exit": 0,
            "stdout": "",
            "stderr": "",
        },
        "command": {
            "exit": 0,
            "stdout": "",
            "stderr": "",
        },
        "points": 0,
        "message": "",
        "markdown": "",
        "success": True, 
    }
    
    # Copy data file?
    if test.get("filename"):
        if os.path.exists(test["filename"]):
            os.remove(test["filename"])
        with open(test["filename"], 'w') as f:
            f.write(test.get("input", ""))

    # Run setup command
    if test.get("setup"):
        try:
            result = subprocess.run(test.get("setup"), capture_output=True, text=True, shell=True, timeout=test.get("timeout", 10))
        except subprocess.TimeoutExpired as e:
            ret["setup"]["exit"] = -1
            ret["setup"]["stdout"] = e.stdout
            ret["setup"]["stderr"] = e.stderr
            ret["success"] = False
            ret["message"] = f"Setup command timed out after {test.get('timeout', 0)} seconds."
            ret["markdown"] = f"Setup command timed out after {test.get('timeout', 0)} seconds.\n\n```\n{e.stderr}\n```"
            return ret
        except Exception as e:
            ret["setup"]["exit"] = -1
            ret["setup"]["stdout"] = ""
            ret["setup"]["stderr"] = str(e)
            ret["success"] = False
            ret["message"] = f"Setup command failed with exception: {str(e)}"
            ret["markdown"] = f"Setup command failed with exception: {str(e)}\n\n```\n{str(e)}\n```"
            return ret
        ret["setup"]["exit"] = result.returncode
        ret["setup"]["stdout"] = result.stdout
        ret["setup"]["stderr"] = result.stderr

        if result.returncode != 0:
            ret["success"] = False
            ret["message"] = result.stderr
            ret["markdown"] = f"Setup command failed with exit code {result.returncode}.\n\n```\n{result.stderr}\n```"
            return ret

    # Run the command
    if test.get("command"):
        try:
            result = subprocess.run(test.get("command"), capture_output=True, text=True, shell=True)
        except subprocess.TimeoutExpired as e:
            ret["command"]["exit"] = -1
            ret["command"]["stdout"] = e.stdout
            ret["command"]["stderr"] = e.stderr
            ret["success"] = False
            ret["message"] = f"Command timed out after {test.get('timeout', 0)} seconds."
            ret["markdown"] = f"Command timed out after {test.get('timeout', 0)} seconds.\n\n```\n{e.stderr}\n```"
            return ret
        except Exception as e:
            ret["command"]["exit"] = -1
            ret["command"]["stdout"] = ""
            ret["command"]["stderr"] = str(e)
            ret["success"] = False
            ret["message"] = f"Command failed with exception: {str(e)}"
            ret["markdown"] = f"Command failed with exception: {str(e)}\n\n```\n{str(e)}\n```"
            return ret
        ret["command"]["exit"] = result.returncode
        ret["command"]["stdout"] = result.stdout
        ret["command"]["stderr"] = result.stderr

        if result.returncode != 0:
            ret["success"] = False
            ret["message"] = result.stderr
            ret["markdown"] = f"Command failed with exit code {result.returncode}.\n\n```\n{result.stderr}\n```"
            return ret

    # Compare output
    if test.get("comparison") == "exact":
        if ret["command"]["stdout"].rtrim() != test.get("output", "").rtrim():
            ret["success"] = False
            ret["message"] = "Output did not match expected output."
            ret["markdown"] = f"Output did not match expected output.\n\nExpected:\n```\n{test.get('output', '')}\n```\n\nGot:\n```\n{ret['command']['stdout']}\n```"
            return ret

    elif test.get("comparison") == "contains":
        if test.get("output", "") not in ret["command"]["stdout"]:
            ret["success"] = False
            ret["message"] = "Output did not contain expected output."
            ret["markdown"] = f"Output did not contain expected output.\n\nExpected to contain:\n```\n{test.get('output', '')}\n```\n\nGot:\n```\n{ret['command']['stdout']}\n```"
            return ret

    elif test.get("comparison") == "regex":
        import re
        if not re.search(test.get("regex", ""), ret["command"]["stdout"]):
            ret["success"] = False
            ret["message"] = "Output did not match expected regex."
            ret["markdown"] = f"Output did not match expected regex.\n\nExpected to match:\n```\n{test.get('regex', '')}\n```\n\nGot:\n```\n{ret['command']['stdout']}\n```"

    elif test.get("comparison") == "loose":
        output = ret["command"]["stdout"].rstrip()
        expected = test.get("output", "").rstrip()

        # Make an array and then filter out blank lines if ignore-blank is set
        output_lines = output.splitlines()
        expected_lines = expected.splitlines()

        if test.get("loose", {}).get("ignore-blank", True):
            output_lines = [line for line in output_lines if line.strip() != ""]
            expected_lines = [line for line in expected_lines if line.strip() != ""]

        # Trim lines if set
        if test.get("loose", {}).get("trim", False):
            output_lines = [line.strip() for line in output_lines]
            expected_lines = [line.strip() for line in expected_lines]
        
        if test.get("loose", {}).get("ltrim", False):
            output_lines = [line.lstrip() for line in output_lines]
            expected_lines = [line.lstrip() for line in expected_lines]

        if test.get("loose", {}).get("rtrim", True):
            output_lines = [line.rstrip() for line in output_lines]
            expected_lines = [line.rstrip() for line in expected_lines]

        # Squash spaces if set
        if test.get("loose", {}).get("squash-spaces", True):
            output_lines = [' '.join(line.split()) for line in output_lines]
            expected_lines = [' '.join(line.split()) for line in expected_lines]

        if output_lines != expected_lines:
            ret["success"] = False
            ret["message"] = "Output did not match expected output."
            ret["markdown"] = f"Output did not match expected output.\n\nExpected:\n```\n{test.get('output', '')}\n```\n\nGot:\n```\n{ret['command']['stdout']}\n```"
        else:
            ret["success"] = True
            ret["message"] = "Output matched expected output."
            ret["markdown"] = f"Output matched expected output.\n\nExpected:\n```\n{test.get('output', '')}\n```\n\nGot:\n```\n{ret['command']['stdout']}\n```"

    else:
        ret["success"] = False
        ret["message"] = f"Unknown comparison method: {test.get('comparison')}"
        ret["markdown"] = f"Unknown comparison method: {test.get('comparison')}"
    return ret

# if __name__ == "__main__":
#     main()
main()