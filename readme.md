# Classroom50 Autograder Script

Customized `autograder.py` file for working with Classroom50 to fallback to the old customized autograding setups that we had with the legacy GitHub Classroom.

> [!NOTE]
> Classroom50 is currently being updated fairly regularly, so these instructions might not be 100% up to date. I'll do my best to keep them updated. 

> [!IMPORTANT]
> You're going to add a file to your classroom repository. When you do this it will override any grading steps that you've defined when you create the assignment in Classroom50. So, you don't need to bother defining tests there when you create assignments if you're using this script. 

## Folder Structure

When you install [Classroom50](https://classroom50.org) to your GitHub organization it will create a private `classroom50` repository where it stores all of its files. This will contain all of your classrooms, information about assignments, and grades. The basic structure looks sort of like this.

```
<org>/classroom50/
    .github/        # Contains workflow files and scripts that can be customized
                    # for the entire organization, but probably shouldn't be
    test-classroom/ # Files specific to a single classroom. The folder name is
                    # the slug from when you built the classroom and shouldn't
                    # be changed later.
```

Each classroom has a folder like `test-classroom` in the example above. 

Inside the classroom folder you'll find the following files

| File | Description |
| --- | --- |
| autograders/ | Folder containing customizations for auto grading individual assignments |
| assignments.json | Information about the individual assignments for your class | 
| autograder.py | The customized autograder script. Probably not there yet. You'll add it in a few steps. |
| classroom.json | Settings for your classroom |
| results.json | Processed results from grading runs |
| scores.json | Processed results from grading runs |
| students.csv | List of your students. |

## Installing the script

Download the latest [release](https://github.com/KatyISD/gh-autograder/releases). The file you want is `autograder.py`. 

Upload or commit and push the `autograder.py` into `/<organization>/classroom50/autograders/`. You will need to do this for any classrom where you want to use this autograder instead of the built in autograder. 

If you want to use the default autograder, but want to use this one for a specific assignment you can also upload to `/<organization>/classroom50/autograders/<assignment-slug>/` and it will only run for submissions on that assignment. 

## tests.yaml

In the `autograders/` folder there may be folders from the slugs of each assignment you created. They're not added by default, but will be used if there. This is where you are going to define your tests. 

> [!TIP]
> If you're going to be working with multiple assignments it's probably best to clone the classroom50 repository locally and push back when you're finished. Each time the repository is updated it runs a series of actions that are needed so that the CR50 web interface can reference the files. 

tests.yaml (or tests.yml) is a file in the `autograders/<assignment-slug>/` folder that defines each individual test you want to run against submitted code. You can have multiple tests, and mix and match types. 

```yaml
tests:
    - name: Test 1
      <...> more settings
    - name: Test 2
      <...> more settings
```

### Shared Setings

| Setting | Default | Notes |
| --- | --- | --- |
| name |  | Required. Display name of the test |
| id |  | Required. Slugged id for the test. Needs to be legal as a dictionary key. |
| type | io | Type of test. Valid options: io - Input output tests, junit4 - JUnit 4 tests, junit or junit5 - JUnit 5 tests, unittest, python, or pyunit - Python unittest tests |
| points | 0 | Number of points for a successful submission | 
| timeout | 10 or 60 | Number of seconds before a test times out and is considered a failure. 10 second default for io, 60 second default for JUnit and Python unittest tests. | 
| partial-credit | false | Whether tests are all-or-nothing or they can get partial credit. Currently only valid for unit tests, io tests are always all-or-nothing. |

### IO Settings

| Setting | Default | Notes |
| --- | --- | --- |
| command | | Required. Command to run the student code. Typically something like `java SomeClass` or `python some_code.py` |
| setup-command | | Runs before the student code to get code ready. Typically used for compilation like `javac SomeClass.java`. | 
| input | | Input for the running program. Will be passes as `stdin` unless `filename` is also defined. |
| input-file | | If defined then this file will be loaded and stored in the `input` property, overwriting anything that's there. The path is relative to the running code so it can be in either the student repository or the `autograder/<slug>/` folder. |
| filename | | If defined then `input` will be stored in this filename and `stdin` will be an empty string. |
| output | | Expected output for the program. |
| output-file | | Same idea as `input-file`, but for the `output` setting | 
| comparison | exact | How to compare expected and produced output for grading. Note that output is always right trimmed before comparison. Valid options are `exact`, `contains`, `regex` and `loose`. |

#### Regex Comparisons

| Setting | Default | Notes | 
| --- | --- | --- |
| regex | | The regular expression string to compare student's output |

#### Loose Comparisons 

The loose comparison method is similar to exact, but lets you omit some comparisons you may not care about. 

| Setting | Default | Notes |
| --- | --- | --- |
| trim | false | Trim the left and right sides of strings before comparing. | 
| ltrim | false | Trim the left side of strings before comparing |
| rtrim | true | Trim the right side of strings before comparing. Note that the right side of the entire string is always trimmed, this only affects multiline strings. |
| ignore-blank | true | If true, removes any blank lines before comparing | 
| squash-spaces | true | If true, squashes multiple whitespace down to a single space before comparing | 

When input or output is a multiline string these affect each line independently, not the string as a whole. 

### JUnit Settings

| Setting | Default | Notes | 
| --- | --- | --- |
| test-class | | Name of the JUnit test class file. If you leave this blank it will run all test classes that match the Maven pattern below. You can also list one specific class like `TestClass` (no extension) or a single method in a class `TestClass#theTestMethod`. |
| lib-path | | Path, relative to the repository root, that contains other files you want in the classpath during build. These will be in the student repository, so they will have access. |

> [!NOTE]
> Maven looks for classes that start with Test or ends with Test, Tests, or TestCase to use as test classes. If you do not define `test-class` then it will run with any found. If you do define `test-class` then it should match this pattern. 

> [!TIP]
> The autograder copies any files from the `autograders/<slug>/` folder to the working directly when running tests, but will overwrite any existing files. This gives you the ability to create new test files that your students don't have access to. For example, if you leave `test-class` empty and give your students `TestA.java`, only `TestA` will run when they test. But you can have `TestB.java` in your autograders folder and both A & B will run on submission. You can also have more tests in a single file with the same name. Ex:, give students `TestC.java` with 5 tests, but have a `TestC.java` in the autograders folder with 20 tests and they'll be graded with the 20 test version when submitted. 

### Python Unit Test Settings

Use `type: unittest` (`python` and `pyunit` are accepted as aliases) to grade with Python's built-in `unittest` module instead of an `io` test. Results are collected and scored the same way as JUnit tests (including `partial-credit`), so the shared settings table above applies here too.

| Setting | Default | Notes |
| --- | --- | --- |
| test-class | | Dotted path to a specific test target, e.g. `tests.test_module` or `tests.test_module.TestClass`, or a single method with `tests.test_module.TestClass.test_method`. If left blank, tests are discovered automatically instead. |
| test-path | . | Directory to start test discovery from when `test-class` isn't set. Same idea as `python -m unittest discover -s`. |
| test-pattern | test*.py | Filename pattern used during discovery when `test-class` isn't set. Same idea as `python -m unittest discover -p`. |
| lib-path | | Path, relative to the repository root, added to `PYTHONPATH` during the test run. These files are in the student repository, so they will have access. |
| setup | | Command run before the student code, useful for any prep steps needed before tests run. |
| setup-timeout | 60 | Number of seconds before the `setup` command times out and is considered a failure. |

> [!NOTE]
> The autograder installs the `unittest-xml-reporting` package automatically the first time a Python unit test runs, so no extra setup is needed in `setup` for it.

> [!TIP]
> Just like the JUnit tip above, files from `autograders/<slug>/` are copied into the working directory before tests run and will overwrite matching student files. This lets you ship a hidden, more complete version of a test file (e.g. give students a `test_hello.py` with a few tests, keep a fuller `test_hello.py` in the autograders folder, and the fuller version is what actually gets graded).

### Example yaml file

```yaml
tests:
    - name: Hello World
      id: hello-world
      type: io
      comparison: exact
      output: Hello World!
      setup: javac HelloWorld.java
      command: java HelloWorld
      points: 30
      timeout: 10
    - name: Exact with files
      id: exact-files
      type: io
      comparison: exact
      input: |-
        1
        2
        3
      output: 6
      filename: in.dat
      points: 40
      timeout: 10
    - name: Unit Test
      id: unit-test
      type: junit4
      timeout: 60
      partial-credit: true
      pints: 40
    - name: Python Unit Test
      id: python-unit-test
      type: unittest
      test-path: tests
      timeout: 60
      partial-credit: true
      points: 40
```

## GitHub Classroom .yaml files

If you're already using either the `compscirocks@autograding-io-grader` or `compscirocks@autograding-junit` actions in an existing student repository from the old GitHub Classroom you can drop that file in `autograders/<slug>` as `tests.yaml` and the autograder script will use it as-is.

The script will automatically parse and convert the old format to new when students submit. There's no reason to convert it yourself. 

Once you copy it to your `classroom50` repository you should remove the orignal from the student template repository. 

## Keeping autograder.py up to date

Updating `autograder.py` by hand in every classroom and `autograders/<slug>/` folder gets tedious once you have more than a couple of classrooms. [sync-autograder.yml](sync-autograder.yml) in this repository is a GitHub Actions workflow template that automates it.

It isn't active here - copy it into your `classroom50` repository as `.github/workflows/sync-autograder.yml`, then run it manually from that repo's Actions tab whenever you want to push out the latest `autograder.py`. It never runs on its own and never adds `autograder.py` to a folder that doesn't already have it - it only overwrites copies that already exist, in:

- `<classroom>/autograder.py`
- `<classroom>/autograders/<assignment-slug>/autograder.py`

To keep a specific folder's copy from being overwritten, drop an empty `.autograder-sync-ignore` file in it (works in either a classroom folder or an `autograders/<slug>/` folder). You can also skip whole top-level classroom folders for a single run with the workflow's `extra_excludes` input.

Once it pushes an update, it also triggers `publish-pages.yaml` directly (via `gh workflow run`) so the republished files show up on GH Pages right away, since a push made with the default `GITHUB_TOKEN` doesn't fire that workflow's own `push` trigger. This relies on `publish-pages.yaml` already accepting `workflow_dispatch` - no other setup needed.