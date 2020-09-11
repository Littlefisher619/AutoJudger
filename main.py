import os
import copy
import subprocess
import platform
import signal
from enum import Enum
import threading
import traceback
import psutil
import time
import json

data_dict = {
    '0.7': {},
    '0.9': {}
}
judge_tasks = {}
score_structure = copy.deepcopy(data_dict)
judge_runner = {
    'types': {
        '.py': 'python3',
        '.jar': 'java',
        '.exe': '',
    },
    'cmd_args': '{orig} {question} {answer}'
}


class JUDGE_STATUS(Enum):
    OK = 0
    CRASH = -1
    TIMEOUT = -2
    UNKOWN_ERROR = -3
    ANSWER_FORMAT_ERROR = -4

def generate_judge_points():
    datas = os.walk(r"data")
    global data_dict, score_structure
    for path, dir_list, file_list in datas:
        for file in file_list:
            file_abs_path = os.path.abspath(os.path.join(path, file))
            data_group = path.split(os.sep)[1].split('_')[1]
            filename, ext = os.path.splitext(file)
            splits = filename.split('_')

            if filename == 'orig':
                data_dict[data_group]['orig'] = file_abs_path
            else:
                operation = splits[2]
                if operation == 'dis':
                    if 'dis' not in data_dict[data_group]:
                        data_dict[data_group]['dis'] = {}
                        score_structure[data_group]['dis'] = {}
                    data_dict[data_group]['dis'][int(splits[3])] = file_abs_path
                    score_structure[data_group]['dis'][int(splits[3])] = None
                else:
                    data_dict[data_group][operation] = file_abs_path
                    score_structure[data_group][operation] = None

    print(data_dict)
    print(score_structure)



def load_judge_tasks():
    global judge_tasks
    src_dir = os.listdir(r'src')

    for stuid in src_dir:
        judge_tasks[stuid] = {}
        cwd = os.path.join(r'src', stuid)
        file_lists = os.listdir(cwd)
        for file in file_lists:
            filename, ext = os.path.splitext(file)
            if ext in ['.py', '.exe', '.jar']:
                judge_tasks[stuid]['type'] = ext
                judge_tasks[stuid]['executable'] = os.path.abspath(os.path.join(cwd, file))
                judge_tasks[stuid]['cwd'] = os.path.abspath(cwd)
                judge_tasks[stuid]['judged'] = False
                break

        if stuid not in judge_tasks:
            print('No available executable file found for', stuid)

        judge_tasks[stuid]['score'] = copy.deepcopy(score_structure)


def kill_process_tree(pid, parent=False):
    p = psutil.Process(pid)
    for child_pro in p.children(recursive=True):
        if child_pro.name() != 'conhost.exe':
            try:
                child_pro.kill()
                print("[-]", child_pro.name(), child_pro.pid, 'killed.')
            except Exception:
                pass

    if parent:
        p.kill()


def limit_memory():
    pid = os.getpid()
    p = psutil.Process(pid)

    while True:
        memory_sum = 0
        for child_pro in p.children(recursive=True):
            info = child_pro.memory_full_info()
            memory = info.uss / (1024 * 1024)
            memory_sum += memory

        info = p.memory_full_info()
        memory = info.uss / (1024 * 1024)
        memory_sum += memory

        if memory_sum > 2048:
            print('[-] Memory exceeds detected!')
            kill_process_tree(pid)
        time.sleep(1)


def taskkill(p):
    print('Taskkill:', p.pid)
    taskkill = subprocess.Popen(['taskkill', '/F', '/T', '/PID', str(p.pid)], stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
    (stdout, errs) = taskkill.communicate()
    stdout = str(stdout.decode('gbk'))
    print(stdout, end='')


def run_cmd(cmd_string, cwd, log_file, timeout=5):

    p = subprocess.Popen(cmd_string, cwd=cwd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                         close_fds=True, start_new_session=True)
    log_and_print(log_file, '[+] Running(%s):' % p.pid, cmd_string)

    format = 'utf-8'
    stderr = stdout = ''

    try:
        (stdout, stderr) = p.communicate(timeout=timeout)
        ret_code = p.poll()
        if ret_code:
            code = JUDGE_STATUS.CRASH
        else:
            code = JUDGE_STATUS.OK
        if stdout is not None:
            stdout = str(stdout.decode(format))
        if stderr is not None:
            stderr = str(stderr.decode(format))
    except subprocess.TimeoutExpired:
        if platform.system() == "Windows":
            log_and_print(log_file, '[-] Timeout!')
            try:
                kill_process_tree(p.pid, True)
            except:
                pass
        else:
            os.killpg(p.pid, signal.SIGTERM)

        code = JUDGE_STATUS.TIMEOUT
    except Exception as e:
        code = JUDGE_STATUS.UNKOWN_ERROR
        traceback.print_exc()

    log_and_print(log_file, '[+] Process(%d) exited.' % p.pid)

    return code, stdout, stderr


def log_and_print(file, *args):
    print(*args)
    print(*args, file=file, flush=True)


if __name__ == '__main__':
    print('Load judge points...')
    generate_judge_points()
    print('Load judge tasks...')
    load_judge_tasks()
    t = threading.Thread(target=limit_memory, daemon=True)
    t.start()

    if os.path.exists('ans.txt'):
        os.remove('ans.txt')

    for stuid, datas in judge_tasks.items():
        print()

        runner = judge_runner['types'][datas['type']]
        arguments = []
        log_file = open(os.path.join('logs', stuid+'.log'), 'w')
        log_and_print(log_file, 'Now juding:', stuid)
        for datagroup in datas['score'].keys():

            for scorepoint in datas['score'][datagroup].keys():
                if scorepoint != 'dis':
                    log_and_print(log_file)
                    log_and_print(log_file, '[+] Test: %s_%s' % (datagroup, scorepoint))

                    ansfile = open('ans.txt', 'w')
                    ansfile.close()

                    anspath = os.path.abspath('ans.txt')
                    arguments = [data_dict[datagroup]['orig'], data_dict[datagroup][scorepoint], anspath]

                    if runner != '':
                        command = [runner, datas['executable']] + arguments
                    else:
                        command = [datas['executable']] + arguments
                    code, stdout, errs = run_cmd(command, datas['cwd'], log_file)

                    if code == JUDGE_STATUS.OK:
                        try:
                            ansfile = open('ans.txt', 'r')
                            answer_str = ansfile.read()
                            answer = float(answer_str)
                            ansfile.close()

                            if answer < 0:
                                code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                                log_and_print(log_file, '[!] Answer', answer, 'is a negative value!')
                            elif answer > 1:
                                code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                                log_and_print(log_file, '[!] Answer', answer, 'is bigger than 1.00!')
                            else:
                                datas['score'][datagroup][scorepoint] = answer

                        except IOError:
                            log_and_print(log_file, '[!] IO ERROR!')
                            code = JUDGE_STATUS.UNKOWN_ERROR
                        except ValueError:
                            traceback.print_exc()
                            log_and_print(log_file, '[!] Answer', answer_str, 'is not a float!')
                            code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                        except TypeError:
                            traceback.print_exc()
                            log_and_print(log_file, '[!] Answer', answer_str, 'is not a float!')
                            code = JUDGE_STATUS.ANSWER_FORMAT_ERROR

                    if code != JUDGE_STATUS.OK:
                        datas['score'][datagroup][scorepoint] = code.value

                    log_and_print(log_file, '[STATUS]', code)
                    log_and_print(log_file, '[STDOUT]', stdout.strip() if stdout else None)
                    log_and_print(log_file, '[STDERR]', errs.strip() if errs else None)
                    log_and_print(log_file, '[ANSWER]', datas['score'][datagroup][scorepoint])

                else:
                    for scorepoint in datas['score'][datagroup]['dis'].keys():
                        log_and_print(log_file)
                        log_and_print(log_file, '[+] Test: %s_dis_%d' % (datagroup, scorepoint))

                        ansfile = open('ans.txt', 'w')
                        ansfile.close()

                        anspath = os.path.abspath('ans.txt')
                        arguments = [data_dict[datagroup]['orig'], data_dict[datagroup]['dis'][scorepoint], anspath]

                        if runner != '':
                            command = [runner, datas['executable']] + arguments
                        else:
                            command = [datas['executable']] + arguments
                        code, stdout, errs = run_cmd(command, datas['cwd'], log_file)

                        if code == JUDGE_STATUS.OK:
                            try:
                                ansfile = open('ans.txt', 'r')
                                answer_str = ansfile.read()
                                answer = float(answer_str)
                                ansfile.close()
                                if answer < 0:
                                    code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                                    log_and_print(log_file, '[!] Answer', answer, 'is a negative value!')
                                else:
                                    datas['score'][datagroup]['dis'][scorepoint] = answer
                                    print()
                            except IOError:
                                log_and_print(log_file, '[!] IO ERROR!')
                                code = JUDGE_STATUS.UNKOWN_ERROR
                            except ValueError:
                                log_and_print(log_file, '[!] Answer', answer_str, 'is not a float!')
                                code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                            except TypeError:
                                log_and_print(log_file, '[!] Answer', answer_str, 'is not a float!')
                                code = JUDGE_STATUS.ANSWER_FORMAT_ERROR

                        if code != JUDGE_STATUS.OK:
                            datas['score'][datagroup]['dis'][scorepoint] = code.value

                        log_and_print(log_file, '[STATUS]', code)
                        log_and_print(log_file, '[STDOUT]', stdout.strip() if stdout else None)
                        log_and_print(log_file, '[STDERR]', errs.strip() if errs else None)
                        log_and_print(log_file, '[ANSWER]', datas['score'][datagroup]['dis'][scorepoint])

        judge_tasks[stuid]['judged'] = True
        log_file.close()
    open('data.json', 'w').write(json.dumps(judge_tasks))
