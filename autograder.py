import datetime
import html
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from pathlib import Path

# Bootstrap any libraries that may not be available
def ensure_package(package_name, import_name=None):
    """
    Ensures that a package is installed. If not, it will attempt to install it
    using pip. This is useful for ensuring that the autograder has all the
    necessary dependencies without requiring the user to manually install them.
    """
    import_name = import_name or package_name

    try:
        return importlib.import_module(package_name)
    except ImportError:
        print(f"Install {import_name}...")
        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            import_name
        ])
        return importlib.import_module(package_name)
    
yaml = ensure_package('yaml', 'PyYAML')    



def assignment_dir():
    """
    Returns the path to the folder where assignment support files
    are stored, or False if it doesn't exist or can't be read.
    """
    parent = Path(__file__).parent
    assignment = os.getenv('ASSIGNMENT', None)

    if not assignment:
        return False

    assignment_directory = parent / os.getenv('ASSIGNMENT')

    if assignment_directory.is_dir():
        return assignment_directory
    
    return False

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
                    'partial-credit': new_with.get('partial-credit', False),

                    # JUnit settings
                    "lib-path": new_with.get("lib-path", ""),
                    'test-class': new_with.get("test-class", ""),
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

    These are relative to assignment_dir(), so they'll need to
    be read from there. 
    """
    
    support_dir = assignment_dir()

    for t in tests.get("tests", []):
        if t.get("input-file") and (support_dir / t.get("input-file", "")).exists():
            t['input'] = Path(support_dir / t.get('input-file')).read_text()
        if t.get("output-file") and (support_dir / t.get('output-file')).exists():
            t['output'] = Path(support_dir / t.get('output-file')).read_text()
    return tests

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
            result = subprocess.run(test.get("command"), capture_output=True, text=True, shell=True, input=stdin, timeout=test.get("timeout", 10))
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
    if test.get("comparison", 'exact') == "exact":
        expected = test.get('output', '')
        actual = ret["command"]["stdout"]

        if test.get('exact', {}).get('ignore-case', False):
            expected = expected.lower()
            actual = actual.lower()

        if expected.rstrip() != actual.rstrip():
            ret["success"] = False
            ret["message"] = "Output did not match expected output"
            ret["markdown"] = markdown_io(
                message = 'Output did not match expected output',
                input = test.get('input'),
                output = ret['command']['stdout'],
                expected = test.get('output')
            )
        else:
            ret["success"] = True
            ret["message"] = "Output matched expected output"
            ret["markdown"] = markdown_io(
                message = 'Output matched expected output',
                input = test.get('input'),
                output = ret['command']['stdout'],
                expected = test.get('output')
            )
    elif test.get("comparison") == "contains":
        expected = test.get("output", "")
        actual = ret["command"]["stdout"]

        if test.get('contains', {}).get('ignore-case', False):
            expected = expected.lower()
            actual = actual.lower()

        if test.get("output", "") not in ret["command"]["stdout"]:
            ret["success"] = False
            ret["message"] = "Output did not contain expected contents"
            ret["markdown"] = markdown_io(
                message = "Output does not contain expected contents",
                input = test.get('input'),
                output = ret['command']['stdout'],
                expected = test.get('output')
            )
        else:
            ret["success"] = True
            ret["message"] = "Output contained expected output."
            ret["markdown"] = f"Output contained expected output.\n\nInput:\n```{test.get('input', '')}\n```\n\nExpected to contain:\n```\n{test.get('output', '')}\n```\n\nYour Output:\n```\n{ret['command']['stdout']}\n```"

    elif test.get("comparison") == "regex":
        if not re.search(test.get("regex", ""), ret["command"]["stdout"]):
            ret["success"] = False
            ret["message"] = "Output did not match regular expression"
            ret["markdown"] = markdown_io(
                message = "Output did not match regular expression",
                input =  test.get('regex'),
                output = ret['command']['stdout'],
                expected = test.get('output', '')
            )
        else:
            ret["success"] = True
            ret["message"] = "Output matched expected regular expression"
            ret["markdown"] =  markdown_io(
                message="Output matched expected regex",
                input=test.get('regex'),
                output=ret['command']['stdout'],
                expected=test.get('output')
            )           

    elif test.get("comparison") == "loose":
        output = ret["command"]["stdout"].rstrip()
        expected = str(test.get("output", "")).rstrip()

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

        # Squash spaces if set, leave one space no matter how many are there
        if test.get("loose", {}).get("squash-spaces", True):
            output_lines = [re.sub(r'[ \t]+', ' ', line) for line in output_lines]
            expected_lines = [re.sub(r'[ \t]+', ' ', line) for line in expected_lines]

        if output_lines != expected_lines:
            ret["success"] = False
            ret["message"] = "Output does not match"
            ret["markdown"] = markdown_io(
                message="Output does not match expected output",
                input=test.get('input'),
                output=ret['command']['stdout'],
                expected=test.get('output')
            )
        else:
            ret["success"] = True
            ret["message"] = "Output matches"
            ret["markdown"] = markdown_io(
                message="Output matched expected output",
                input=test.get('input'),
                output=ret['command']['stdout'],
                expected=test.get('output')
            )
            
    else:
        ret["success"] = False
        ret["message"] = f"Unknown comparison method: {test.get('comparison')}"
        ret["markdown"] = f"Unknown comparison method: {test.get('comparison')}"

    
    return ret

_MAVEN_HELP_BOILERPLATE = (
    'Re-run Maven using',
    'To see the full stack trace',
    'For more information about the errors',
    '-> [Help',
    'http://cwiki.apache.org',
)
_MAVEN_DIVIDER = re.compile(r'^\[INFO\]\s*-{5,}\s*$')

def summarize_maven_failure(output):
    """
    Maven's full build log is mostly plugin/dependency-resolution noise -
    what the student actually needs to see is just the compiler error (or
    whichever [ERROR] lines explain the failure), not the whole transcript.
    """
    lines = output.splitlines()

    # Most common case: a compile error, bounded by the two "----" dividers
    # Maven prints immediately before and after the "COMPILATION ERROR" block.
    start = next((i for i, line in enumerate(lines) if 'COMPILATION ERROR' in line), None)
    if start is not None:
        end = len(lines)
        seen_divider = False
        for i in range(start + 1, len(lines)):
            if _MAVEN_DIVIDER.match(lines[i]):
                if seen_divider:
                    end = i + 1
                    break
                seen_divider = True
        return '\n'.join(lines[start:end]).strip()

    # Otherwise, fall back to just the [ERROR] lines, skipping Maven's
    # generic "how to get more help" boilerplate at the very end.
    error_lines = [
        line for line in lines
        if line.strip().startswith('[ERROR]') and not any(marker in line for marker in _MAVEN_HELP_BOILERPLATE)
    ]
    if error_lines:
        return '\n'.join(error_lines).strip()

    return output.strip()

def score_xml_test_results(xml_files, test, result, label='Test', on_missing=None, summarize_build_output=None):
    """
    Shared scoring/markdown logic for any test type that reports results as
    JUnit-style XML (testsuite/testcase, with failure/error/skipped children).
    Used by both the JUnit runner and the Python unittest runner so the two
    produce matching output.
    """
    ret = {
        "command": {
            "exit": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
        "points": test.get('points', 0),    # Total points available
        "score": 0,     # Points scored by student submission
        "message": "",
        "markdown": "",
        "success": True,
    }

    if not xml_files:
        print('No XML Files Found\n')
        print(f'{label} Results')
        print(result)

        if on_missing:
            on_missing()

        ret["success"] = False

        # A non-zero exit with no XML reports almost always means the build/
        # compile step itself failed before any tests could run, rather than
        # the tests running and simply producing no results. Call that out
        # distinctly so it's not confused with "0 tests found".
        if result.returncode != 0:
            build_output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            if summarize_build_output:
                build_output = summarize_build_output(build_output)
            ret["message"] = f"{label} build failed"
            ret["markdown"] = f"**{label} build failed** (exit code {result.returncode}) before any tests could run.\n\n```\n{build_output}\n```"
        else:
            ret["message"] = f"No {label} test results found."
            ret["markdown"] = f"No {label} test results found.\n\nNo XML reports found\n\n```\n{result.stderr}\n```"
        return ret

    test_results = {
        'count': 0,
        'failures': 0,
        'errors': 0,
        'skipped': 0,
        'successes': 0,
        'total_points': test.get('points', 0),
        'time': 0,
        'markdown': '',
        'tests': []
    }

    for x in xml_files:
        tree = ET.parse(x)
        root = tree.getroot()
        for testcase in root.findall('testcase'):
            test_result = {
                "time": float(testcase.get('time', 0)),
                "name": testcase.get('name', ''),
                "classname": testcase.get('classname', ''),
                "passed": False,
                "status": ""
            }

            failure = testcase.find('failure')
            error = testcase.find('error')
            skipped = testcase.find('skipped')

            if failure is not None:
                test_result['passed'] = False
                test_result['status'] = 'failure'
                test_result['message'] = failure.get('message', '')
                test_results['failures'] += 1
                ret['success'] = False
            elif error is not None:
                test_result['passed'] = False
                test_result['status'] = 'error'
                test_result['message'] = error.get('message', '')
                test_results['errors'] += 1
                ret['success'] = False
            elif skipped is not None:
                test_result['passed'] = False
                test_result['status'] = 'skipped'
                test_result['message'] = skipped.get('message', '')
                test_results['skipped'] += 1
                ret['success'] = False
            else:
                test_result['passed'] = True
                test_result['status'] = 'success'
                test_result['message'] = ''
                test_results['successes'] += 1

            test_results['count'] += 1
            test_results['time'] += float(testcase.get('time', 0))
            test_results['tests'].append(test_result)

    if test_results['count'] == 0:
        ret["success"] = False
        ret["message"] = f"No {label} test cases found."
        ret["markdown"] = f"No {label} test cases found.\n\nNo tests found in XML files\n\n```\n{result.stderr}\n```"
        return ret

    # Build the message for the results header
    messages = []
    if test_results['successes'] >= 1:
        messages.append(str(test_results['successes']) + ' ' + ('tests' if test_results['successes'] > 1 else 'test') + ' passed')
    if test_results['failures'] >= 1:
        messages.append(str(test_results['failures'])  + ' ' + ('tests' if test_results['failures'] > 1 else 'test') + ' failed')
    if test_results['errors'] >= 1:
        messages.append(str(test_results['errors']) + ' ' + ('tests' if test_results['errors'] > 1 else 'test') + ' had errors')
    if test_results['skipped'] >= 1:
        messages.append(str(test_results['skipped']) + ' ' + ('tests' if test_results['skipped'] > 1 else 'test') + ' skipped')

    ret['message'] = ', '.join(messages)

    # Have to go back through now that we have them all and assign points
    # and build markdown table. There is already some data coming out of
    # the test results returned, so we don't need to duplicated that.
    total_tests = test_results['count']
    md = f"<table>\n\t<tr>\n\t\t<th>Test Name</th>\n\t\t<th>Results</th>{ '<th>Points</th>' if test.get('partial-credit', True) else '' }\n\t\t<th>Message</th>\n\t</tr>\n"

    for t in test_results['tests']:
        partial_points = 0
        md += f"\t<tr>\n\t\t<td>{t['name']}</td>\n\t\t<td>"
        if t.get('status') == 'success':
            md += ":white_check_mark:"
            partial_points += test.get('points', 0) / total_tests
            # Only accumulate score during loop if partial credit is enabled
            if test.get('partial-credit', True):
                ret['score'] += partial_points
        elif t.get('status') == 'failure':
            md += ":no_entry_sign:"
        elif t.get('status') == 'error':
            md += ":warning:"
        elif t.get('status') == 'skipped':
            md += ":grey_question:"
        md += f"</td>\n"

        if test.get('partial-credit', True):
            md += f"\t\t<td>{ round(partial_points, 2) }</td>\n"

        md += f"\t\t<td style='white-space:pre-wrap;'>"
        if t.get('status') == 'success':
            md += 'Test passed'
        else:
            md += html.escape(t.get('message', ''))
        md += f"</td>\n"

        md += f"\t</tr>\n"

    # If partial credit is disabled, apply all-or-nothing scoring
    if not test.get('partial-credit', True):
        if test_results['successes'] == test_results['count']:
            ret['score'] = test.get('points', 0)
        else:
            ret['score'] = 0

    # Summary line, only if partial credit
    if test.get('partial-credit', True):
        md += f"\t<tr>\n\t\t<td></td>\n"
        md += f"\t\t<td style='font-weight:bold;text-align:right;'>Total:</td>\n"
        md += f"\t\t<td style='font-weight:bold;'>{ round(ret['score'], 2) }</td>\n"
        md += f"\t\t<td></td>\n\t</tr>\n"
    md += f"</table>\n"

    test_results['markdown'] = md
    ret['markdown'] = md

    return ret

def test_junit4(test):
    """
    Runs the JUnit tests on submitted code. The junit jars can be either
    in the lib-path defined or already on the image.
    """
    build_pom(test)

    mvn_command = ['mvn', 'clean', 'test']
    if test.get('test-class', '') != '':
        mvn_command.append(f'-Dtest={test.get("test-class")}')

    try:
        result = subprocess.run(mvn_command, capture_output=True, text=True, shell=False, timeout=test.get("timeout", 60))
    except subprocess.TimeoutExpired as e:
        return {
            "command": {"exit": -1, "stdout": e.stdout, "stderr": e.stderr},
            "points": test.get('points', 0),
            "score": 0,
            "success": False,
            "message": f"JUnit command timed out after {test.get('timeout', 0)} seconds.",
            "markdown": f"JUnit command timed out after {test.get('timeout', 0)} seconds.\n\n```\n{e.stderr}\n```",
        }

    # Glob for the xml files
    surefire_reports_dir = Path('target/surefire-reports')
    xml_files = list(surefire_reports_dir.glob('TEST-*.xml'))

    def print_pom_debug():
        print('pom.xml contents')
        print(Path('pom.xml').read_text())

    ret = score_xml_test_results(
        xml_files, test, result,
        label='JUnit',
        on_missing=print_pom_debug,
        summarize_build_output=summarize_maven_failure,
    )

    subprocess.run(['mvn', 'clean'], capture_output=True, text=True, shell=False)
    Path('pom.xml').unlink()  # Clean up the pom.xml after building it
    return ret

def test_python_unittest(test):
    """
    Runs Python unittest-based tests against the student's submission.
    Discovery mirrors `python -m unittest discover` (test-path/test-pattern),
    or a specific dotted test target can be given via test-class, same as
    JUnit's test-class. Results come back as JUnit-style XML via the
    xmlrunner package so they can be scored with the same logic as JUnit.
    """
    ensure_package('xmlrunner', 'unittest-xml-reporting')

    reports_dir = Path('xmlrunner-reports')
    if reports_dir.exists():
        shutil.rmtree(reports_dir)
    reports_dir.mkdir(parents=True)

    env = os.environ.copy()
    lib_dir = test.get('lib-path', '')
    if lib_dir and Path(lib_dir).is_dir():
        env['PYTHONPATH'] = str(Path(lib_dir).resolve()) + os.pathsep + env.get('PYTHONPATH', '')

    test_class = test.get('test-class', '')
    if test_class:
        command = [sys.executable, '-m', 'xmlrunner', '-o', str(reports_dir), test_class]
    else:
        command = [
            sys.executable, '-m', 'xmlrunner', 'discover',
            '-o', str(reports_dir),
            '-s', test.get('test-path', '.'),
            '-p', test.get('test-pattern', 'test*.py'),
        ]

    # Run setup command, if it's there
    setup_command = test.get('setup', '')
    if setup_command:
        setup_result = subprocess.run(
            setup_command,
            capture_output=True,
            text=True,
            shell=True,
            env=env,
            timeout=test.get('setup-timeout', 60)
        )

        if setup_result.returncode != 0:
             return {
                "command": {"exit": setup_result.returncode, "stdout": setup_result.stdout, "stderr": setup_result.stderr},
                "points": test.get("points", 0),
                "score": 0,
                "success": False,
                "message": "Setup command failed before running tests.",
                "markdown": f"Setup command failed...\n\n```{setup_result.stderr}```",
            }

    try:
        result = subprocess.run(command, capture_output=True, text=True, shell=False, env=env, timeout=test.get('timeout', 60))
    except subprocess.TimeoutExpired as e:
        return {
            "command": {"exit": -1, "stdout": e.stdout, "stderr": e.stderr},
            "points": test.get('points', 0),
            "score": 0,
            "success": False,
            "message": f"Python unittest command timed out after {test.get('timeout', 0)} seconds.",
            "markdown": f"Python unittest command timed out after {test.get('timeout', 0)} seconds.\n\n```\n{e.stderr}\n```",
        }

    xml_files = list(reports_dir.glob('TEST-*.xml')) if reports_dir.exists() else []

    ret = score_xml_test_results(xml_files, test, result, label='Python unittest')

    shutil.rmtree(reports_dir, ignore_errors=True)

    return ret

def markdown_io(message = 'Output matched', input='', output='', expected=''):
    md = ''

    if message:
        md += f"**{message}**\n\n"
    if input:
        md += f"Input:\n"
        md += f"```\n"
        md += input + "\n"
        md += f"```\n\n"
    if output:
        md += f"Your Output:\n"
        md += f"```\n"
        md += output + "\n"
        md += f"```\n\n"
    if expected:
        md += f"Expected Output:\n"
        md += f"```\n"
        md += expected + "\n"
        md += f"```\n\n"
    return md

def copy_support_files():
    """
    Copies files from the <repo>/autograders/<slug> folder so they can be
    used as part of the grading process. This intentionally omits the 
    tests.{yml,yaml} file since it's not part of the actual run.

    Any files that exist in the student repository and the support files will
    be overwritten by the support version. This is so you can include more 
    detailed test cases if wanted.
    """

    print('Copying support files from ' + str(assignment_dir()))

    if not assignment_dir(): 
        print('Support directory not available')
        return

    # Print list of files
    for item in assignment_dir().iterdir():
        print(f" - {item.name}")

    print('Current Folder contents - Path(.)')
    print(Path('.').resolve())
    for item in Path('.').iterdir():
        print(f" - {item.name}")

    print('cwd()')
    print(Path.cwd().resolve())

    shutil.copytree(
        assignment_dir(), 
        Path.cwd(), 
        dirs_exist_ok=True, 
        ignore=shutil.ignore_patterns('tests.yaml', 'tests.yml')
    )
    print('After copy')
    for item in Path('.').iterdir():
        print(f" - {item.name}")

def build_pom(test):

    src_dir = test.get('src-path', '.')
    test_dir = test.get('test-path', '.')

    lib_dir = test.get('lib-path', '')

    if lib_dir and Path(lib_dir).is_dir():
        lib_dir_full = Path(lib_dir).resolve()

        # additionalClasspathElement/-cp add each entry as a literal directory
        # or jar path - neither expands jars sitting inside a directory - so
        # each jar has to be listed individually. The directory itself is kept
        # too, in case it also has loose .class files.
        lib_classpath_entries = sorted(str(p) for p in lib_dir_full.glob('*.jar')) + [str(lib_dir_full)]

        lib_dir_surefire = """
            <additionalClasspathElements>
""" + "\n".join(
            "                <additionalClasspathElement>" + entry + "</additionalClasspathElement>"
            for entry in lib_classpath_entries
        ) + """
            </additionalClasspathElements>
            """
        # -cp on the compiler plugin replaces the whole classpath rather than
        # appending to it, so the dependency classpath has to be captured via
        # maven-dependency-plugin first and combined with the lib dir here,
        # otherwise junit/hamcrest silently drop off the compile classpath.
        lib_dir_compiler = """
            <arg>-cp</arg>
            <arg>${compile.classpath}${path.separator}""" + os.pathsep.join(lib_classpath_entries) + """</arg>
            """
        dependency_plugin = """
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
                <executions>
                    <execution>
                        <id>build-classpath</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>build-classpath</goal>
                        </goals>
                        <configuration>
                            <outputProperty>compile.classpath</outputProperty>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
            """
    else:
        lib_dir_surefire = ""
        lib_dir_compiler = ""
        dependency_plugin = ""

    # Get the junit version
    junit_version = test.get('type', 'junit')
    if junit_version == 'junit4':
        junit_xml = """
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.13.2</version>
        </dependency>
        <dependency>
            <groupId>org.hamcrest</groupId>
            <artifactId>hamcrest</artifactId>
            <version>3.0</version>
        </dependency>
        """
    elif (junit_version == 'junit5' or junit_version == 'junit'):
        junit_xml = """
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
        </dependency>
        """

    """
    Build the pom.xml file for junit4 tests
    """
    xml = """<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.example</groupId>
    <artifactId>assignment</artifactId>
    <version>1.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>""" + junit_xml + """        
    </dependencies>

    <build>
        <sourceDirectory>""" + src_dir + """</sourceDirectory>
        <testSourceDirectory>""" + test_dir + """</testSourceDirectory>

        <plugins>""" + dependency_plugin + """
            <plugin>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <includes>
                        <include>**/*.java</include>
                    </includes>
                    <compilerArgs>
                    """ + lib_dir_compiler + """
                    </compilerArgs>
                </configuration>
            </plugin>

            <plugin>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.6</version>
                <configuration>
                """ + lib_dir_surefire + """
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>"""
    Path('pom.xml').write_text(xml)

def main(): 
    # Check if tests.yaml or tests.yml exists in the current directory
    # or its __file__ parent, start with parent since that's more likely
    support_dir = assignment_dir()
    
    if support_dir and (support_dir / 'tests.yaml').exists(): #os.path.exists('../tests.yaml'):
        with (support_dir / 'tests.yaml').open('r', encoding="utf-8") as file:
            tests = yaml.safe_load(file)
    elif support_dir and (support_dir / 'tests.yml').exists(): #os.path.exists('../tests.yml'):
        with (support_dir / 'tests.yml').open('r', encoding="utf-8") as file:
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

    copy_support_files()
    tests = normalize_tests(tests)
    tests = load_io(tests)

    status = {
        "points": 0,
        "score": 0,
        "points_available": 0,
        "tests_run": 0,
    }

    test_info = []

    # Iterate through tests and run the individual tests
    for t in tests.get('tests', []):
        print(f"Running test: {t.get('name', '')} ({t.get('type', 'io')})")
        status["tests_run"] += 1
        status["points_available"] += t.get("points", 0)

        test_results = {
            "test-name": t.get("name", ""),
            "passed": False,
            "score": 0,
            "max-score": t.get("points", 0),
            "message": "",
            "markdown": "",
        }

        # IO is default test type
        if t.get("type", "io") == "io":
            result = test_io(t)

            if result["success"]:
                status["score"] += t.get("points", 0)
                test_results["passed"] = True
                test_results["score"] = t.get("points", 0)

            test_results["markdown"] = result.get("markdown", "")
            test_results["message"] = result.get("message", "")
        elif t.get('type') in ['junit', 'junit4', 'junit5']:
            result = test_junit4(t)
            if result['success']:
                test_results['passed'] = True
            # Partial-credit scoring divides points across test cases, which
            # always yields a float in Python (even for a whole number like
            # 10.0) - result.json requires score/max-score to be strict ints,
            # so round to a whole point here before it's ever written out.
            score = round(result.get('score', 0))
            status['score'] += score
            test_results['score'] = score

            test_results['markdown'] = result.get('markdown', '')
            test_results['message'] = result.get('message', '')
        elif t.get('type') in ['unittest', 'python', 'pyunit']:
            result = test_python_unittest(t)
            if result['success']:
                test_results['passed'] = True
            score = round(result.get('score', 0))
            status['score'] += score
            test_results['score'] = score

            test_results['markdown'] = result.get('markdown', '')
            test_results['message'] = result.get('message', '')

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
        "score": status["score"],
        "max-score": status["points_available"],
        "tests": test_info,
    }

    # Build the markdown for results
    test_markdown = ''
    results_header = '## Autograder Results\n\n'
    results_header += f"<table><tr><th>Test Name</th><th>Passed</th><th>Score</th><th>out of</th><th>Message</th></tr>\n\n"

    # print(json.dumps(test_info, indent=2))

    for test in test_info:
        test_markdown += f"### Results: {test['test-name']}\n\n"
        test_markdown += f"**Score:** { round(test['score'], 2)} / {test['max-score']}\n\n"
        test_markdown += f"**Passed:** {'Yes' if test['passed'] else 'No'}\n\n"

        test_markdown += test['markdown'] + "\n\n"

        results_header += f"<tr><td>{test['test-name']}</td><td>"
        
        if test['passed']:
            results_header += ":white_check_mark:"
        elif test['score'] == 0:
            results_header += ":no_entry_sign:"
        else:
            results_header += ":warning:"

        results_header += f"</td><td>{ round(test['score'], 2) }</td><td>{test['max-score']}</td><td>{test['message']}</td></tr>"
    
    results_header += f"<tr><td><b>Totals</b></td><td></td><td><b>{ round(status['score'], 2) }</b></td><td><b>{status['points_available']}</b></td></tr>"
    results_header += f"</table>\n\n"

    results_header += f"---\n\n### Individual Tests\n\n"

    # write the file
    Path('result.json').write_text(json.dumps(data, indent=2) + "\n")

    # Write the markdown file
    md = results_header + test_markdown

    Path('release-body.md').write_text(md)

main()
