import datetime
import json
import os
import yaml
import subprocess
import sys

from pathlib import Path


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
    # or its __file__ parent, start with parent since that's more likely
    parent = Path(__file__).parent
    assignment_dir = parent / os.getenv('ASSIGNMENT', '')
    
    if (assignment_dir / 'tests.yaml').exists(): #os.path.exists('../tests.yaml'):
        with (assignment_dir / 'tests.yaml').open('r', encoding="utf-8") as file:
            tests = yaml.safe_load(file)
    elif (assignment_dir / 'tests.yml').exists(): #os.path.exists('../tests.yml'):
        with (assignment_dir / 'tests.yml').open('r', encoding="utf-8") as file:
            tests = yaml.safe_load(file)
    elif os.path.exists('tests.yaml'):
        with open('tests.yaml', 'r') as file:
            tests = yaml.safe_load(file)
    elif os.path.exists('tests.yml'):
        with open('tests.yml', 'r') as file:
            tests = yaml.safe_load(file)
    else:
        # Just exit, it'll be a no test run. Still needs to build
        # result.json so runner knows nothing ran
        data = {
            "schema": "classroom50/result/v1",
            "classroom": os.getenv('CLASSROOM', ''),
            "assignment": os.getenv('ASSIGNMENT', ''),
            "assignment_type": os.getenv('MODE', ''),
            "owner": os.getenv('USERNAME') or os.getenv('USERNAME'),
            "submission": os.getenv('SUBMISSION_TAG', ''),
            "commit": os.getenv('COMMIT_URL', ''),
            "release": os.getenv('RELEASE_URL', ''),
            "review": os.getenv('REVIEW_URL') or os.getenv('COMMIT_URL', ''),
            "datetime": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), 
            "score": 0,
            "max-score": 0,
            "tests": []
        }
        Path('result.json').write_text(json.dumps(data, indent=2) + "\n")
        sys.exit(0)

    tests = normalize_tests(tests)
    tests = load_io(tests)

    status = {
        "points": 0,
        "points_available": 0,
        "tests_run": 0,
    }

    test_info = []

    # Iterate through tests and run the individual tests
    for t in tests.get('tests', []):
        status["tests_run"] += 1
        status["points_available"] += t.get("points", 0)

        test_results = {
            "test-name": t.get("name", ""),
            "passed": False,
            "score": 0,
            "max-score": t.get("points", 0),
        }

        if t.get("type") == "io":
            result = test_io(t)
            
            if result["success"]:
                status["points"] += t.get("points", 0)
                test_results["passed"] = True
                test_results["score"] = t.get("points", 0)

            test_results["markdown"] = result.get("markdown", "")
        
        test_info.append(test_results)

    # Tests have run, create the results.json file
    data = {
        "schema": "classroom50/result/v1",
        "classroom": os.getenv('CLASSROOM', ''),
        "assignment": os.getenv('ASSIGNMENT', ''),
        "assignment_type": os.getenv('MODE', ''),
        "owner": os.getenv('USERNAME') or os.getenv('USERNAME'),
        "submission": os.getenv('SUBMISSION_TAG', ''),
        "commit": os.getenv('COMMIT_URL', ''),
        "release": os.getenv('RELEASE_URL', ''),
        "review": os.getenv('REVIEW_URL') or os.getenv('COMMIT_URL', ''),
        "datetime": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), 
        "score": status["points"],
        "max-score": status["points_available"],
        "tests": test_info,
    }

    # Build the markdown for results
    test_markdown = ''
    results_header = '## Autograder Results\n\n'
    results_header += f"<table><tr><th>Test Name</th><th>Passed</th><th>Score</th><th>Points</th><th>Message</th></tr>\n\n"

    for test in test_info:
        test_markdown += f"#### {test['test-name']}\n\n"
        test_markdown += f"**Score:** {test['score']} / {test['max-score']}\n\n"
        test_markdown += f"**Passed:** {'Yes' if test['passed'] else 'No'}\n\n"

        test_markdown += test['markdown'] + "\n\n"

        results_header += f"<tr><td>{test['test-name']}</td><td>"
        
        if test['score'] == test['max-score']:
            results_header += ":white_check_mark:"
        elif test['score'] == 0:
            results_header += ":no_entry_sign:"
        else:
            results_header += ":warning:"

        results_header += f"</td><td>{test['score']}</td><td>{test['max-score']}</td><td>{test['message']}</td></tr>"
    
    results_header += f"<tr><td><b>Totals</b></td><td></td><td><b>{status['points']}</b></td><td><b>{status['points_available']}</b></td></tr>"
    results_header += f"</table>\n\n"

    results_header += f"---\n\n### Individual Tests\n\n"

    # write the file
    Path('result.json').write_text(json.dumps(data, indent=2) + "\n")

    # Write the markdown file
    md = results_header + test_markdown

    Path('release-body.md').write_text(md)


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
    
    # Copy data file or stdin
    stdin = ""
    if test.get('input', ''):
        if test.get("filename"):
            if os.path.exists(test["filename"]):
                os.remove(test["filename"])
            with open(test["filename"], 'w') as f:
                f.write(test.get("input", ""))
        else:
            stdin = test.get("input", "")

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
            result = subprocess.run(test.get("command"), capture_output=True, text=True, shell=True, input=stdin)
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
        expected = test.get('output', '')
        actual = ret["command"]["stdout"]

        if test.get('exact', {}).get('ignore-case', False):
            expected = expected.lower()
            actual = actual.lower()

        if expected.rtrim() != actual.rtrim():
            ret["success"] = False
            ret["message"] = "Output did not match expected output."
            ret["markdown"] = f"Output did not match expected output.\n\nExpected:\n```\n{test.get('output', '')}\n```\n\nYour Output:\n```\n{ret['command']['stdout']}\n```"
            return ret
        else:
            ret["success"] = True
            ret["message"] = "Output matched expected output."
            ret["markdown"] = f"Output matched expected output.\n\nExpected:\n```\n{test.get('output', '')}\n```\n\nGot:\n```\n{ret['command']['stdout']}\n```"

    elif test.get("comparison") == "contains":
        expected = test.get("output", "")
        actual = ret["command"]["stdout"]

        if test.get('contains', {}).get('ignore-case', False):
            expected = expected.lower()
            actual = actual.lower()

        if test.get("output", "") not in ret["command"]["stdout"]:
            ret["success"] = False
            ret["message"] = "Output did not contain expected output."
            ret["markdown"] = f"Output did not contain expected output.\n\nExpected to contain:\n```\n{test.get('output', '')}\n```\n\nYour Output:\n```\n{ret['command']['stdout']}\n```"
            return ret
        else:
            ret["success"] = True
            ret["message"] = "Output contained expected output."
            ret["markdown"] = f"Output contained expected output.\n\nExpected to contain:\n```\n{test.get('output', '')}\n```\n\nYour Output:\n```\n{ret['command']['stdout']}\n```"

    elif test.get("comparison") == "regex":
        import re
        if not re.search(test.get("regex", ""), ret["command"]["stdout"]):
            ret["success"] = False
            ret["message"] = "Output did not match expected regex."
            ret["markdown"] = f"Output did not match expected regex.\n\nExpected to match:\n```\n{test.get('regex', '')}\n```\n\nYour Output:\n```\n{ret['command']['stdout']}\n```"
            return ret
        else:
            ret["success"] = True
            ret["message"] = "Output matched expected regex."
            ret["markdown"] = f"Output matched expected regex.\n\nExpected to match:\n```\n{test.get('regex', '')}\n```\n\nYour Output:\n```\n{ret['command']['stdout']}\n```"

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
            ret["markdown"] = f"Output matched expected output.\n\n```\n{ret['command']['stdout']}\n```"

    else:
        ret["success"] = False
        ret["message"] = f"Unknown comparison method: {test.get('comparison')}"
        ret["markdown"] = f"Unknown comparison method: {test.get('comparison')}"

    
    return ret

main()