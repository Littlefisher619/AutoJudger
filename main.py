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
import re
from studentlist import student_list
data_dict = {
    '0.7': {},
    '0.9': {}
}
judge_tasks = {}
score_structure = copy.deepcopy(data_dict)
judge_runner = {
    'types': {
        '.py': ['python3', ],
        '.jar': ['java', '-jar'],
        '.exe': [],
    },
}


class JUDGE_STATUS(Enum):
    OK = 0
    CRASH = -1
    TIMEOUT = -2
    UNKNOWN_ERROR = -3
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
        task = {}
        cwd = os.path.join(r'src', stuid)
        file_lists = os.listdir(cwd)
        for file in file_lists:
            filename, ext = os.path.splitext(file)
            if ext in ['.py', '.exe', '.jar'] and filename == 'main':
                task['type'] = ext
                task['executable'] = os.path.abspath(os.path.join(cwd, file))
                task['cwd'] = os.path.abspath(cwd)
                task['judged'] = False
                task['score'] = copy.deepcopy(score_structure)
                judge_tasks[stuid] = task
                print('[+] Task:', stuid, file)
                break

        if stuid not in judge_tasks:
            print('[!] No available executable file found for', stuid)
            print('[!] Files: ', file_lists)
    print('Load', len(judge_tasks), 'tasks.')

    print('Here are students without available executable file:')
    print(list(set(student_list).difference(set(judge_tasks.keys()))))


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
            try:
                kill_process_tree(pid)
            except Exception:
                print('Failed to kill process', pid)
                traceback.print_exc()
        time.sleep(1)


def parse_score_data(file):
    """
    解析测试点数据，结果存放到 score.json 文件, 同时 scores 文件夹里存放每个人的成绩
    score 字段指总扣分
    dec 字段标注它是否是有保持递减关系
    detail 是各个测试点扣分详情
    :param file:
    :return:
    """
    if not os.path.exists('./scores'):
        os.mkdir('./scores')
    score = {}
    data = json.load(open(file))
    test_groups = None
    # test_groups = [str(test_group) for test_group in sorted([float(k) for k in task_key])]
    for stuid, studata in data.items():
        if test_groups is None:
            test_groups = [str(test_group) for test_group in sorted([float(k) for k in studata['score'].keys()])]
        score[stuid] = {}
        detail = copy.deepcopy(studata['score'])
        score[stuid]['detail'] = detail
        score[stuid]['dec'] = True
        score[stuid]['score'] = 0
        dec_list = []
        test_points = []
        for test_group, result_group in studata['score'].items():
            for test_point, result_point in result_group.items():
                test_points.append(test_point)
                if isinstance(result_point, dict):
                    for k, v in result_point.items():
                        if not (isinstance(v, float) and 0 < v < 1):
                            detail[test_group][test_point][k] = -2
                            score[stuid]['score'] -= 2
                        else:
                            detail[test_group][test_point][k] = 0
                        dec_list.append([result_point[str(key)] for key in
                                         sorted([int(k) for k in result_point.keys()], reverse=True) if
                                         isinstance(result_point[str(key)], float) and 0 <= result_point[str(key)] <= 1])
                elif not isinstance(result_point, float) \
                        or (test_point == 'orig' and result_point != 1) \
                        or result_point < 0 or result_point > 1:
                    detail[test_group][test_point] = -2
                    score[stuid]['score'] -= 2
                else:
                    detail[test_group][test_point] = 0
        for test_point in test_points:
            dec_list.append([studata['score'][test_group][test_point] for test_group in test_groups
                             if isinstance(studata['score'][test_group][test_point], float)
                             and 0 <= studata['score'][test_group][test_point] <= 1])
        score[stuid]['dec'] = all([all([x <= y for x, y in zip(dec, dec[1:]) if x and y]) for dec in dec_list])
        open(f'./scores/{stuid}.json', 'w').write(json.dumps(score[stuid]))
    open('score.json', 'w').write(json.dumps(score))
    print(json.dumps(score))


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
            try:
                stdout = str(stdout.decode(format))
            except UnicodeDecodeError:
                format = 'gbk'
                stdout = str(stdout.decode(format))
            except Exception:
                log_and_print(log_file, '[!] Cannot decode data from STDOUT')
                log_and_print(log_file, traceback.format_exc())


        if stderr is not None:
            try:
                stderr = str(stderr.decode(format))
            except UnicodeDecodeError:
                format = 'gbk'
                stderr = str(stderr.decode(format))
            except Exception:
                log_and_print(log_file, '[!] Cannot decode data from STDERR')
                log_and_print(log_file, traceback.format_exc())
    except subprocess.TimeoutExpired:
        if platform.system() == "Windows":
            log_and_print(log_file, '[-] Timeout!')
            try:
                kill_process_tree(p.pid, True)
            except Exception:
                print('Failed to kill process', p.pid)
                traceback.print_exc()
                pass
        else:
            os.killpg(p.pid, signal.SIGTERM)

        code = JUDGE_STATUS.TIMEOUT
    except Exception as e:
        log_and_print(log_file, '[!] Unknown Error while executing the process!')
        log_and_print(log_file, traceback.format_exc())
        code = JUDGE_STATUS.UNKNOWN_ERROR


    log_and_print(log_file, '[+] Process(%d) exited.' % p.pid)

    return code, stdout, stderr


def log_and_print(file, *args):
    print(*args)
    print(*args, file=file, flush=True)

def do_judge_task():
    t = threading.Thread(target=limit_memory, daemon=True)
    t.start()

    if os.path.exists('ans.txt'):
        os.remove('ans.txt')

    for stuid, datas in judge_tasks.items():
        print()

        runner = judge_runner['types'][datas['type']]
        arguments = []
        log_file = open(os.path.join('logs', stuid+'.log'), 'w', encoding='utf-8')
        result_json = open(os.path.join('results', stuid+'.json'), 'w', encoding='utf-8')
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

                    command = runner + [datas['executable'], ] + arguments
                    code, stdout, errs = run_cmd(command, datas['cwd'], log_file)

                    if code == JUDGE_STATUS.OK:
                        try:
                            ansfile = open('ans.txt', 'r')
                            answer_str = ansfile.read()
                            if '%' in answer_str:
                                res = re.findall('(\d+)\.\d+%', answer_str)
                                if len(res) != 1:
                                    raise ValueError('Cannot find answer in',answer_str)
                                answer_str = "0." + res[0]
                            else:
                                res = re.findall('(0\.\d+)', answer_str)
                                if len(res) != 1:
                                    raise ValueError('Cannot find answer in',answer_str)
                                answer_str = res[0]

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

                        except ValueError:
                            log_and_print(log_file, '[!] Answer', answer_str, 'is not a float!')
                            log_and_print(log_file, traceback.format_exc())
                            code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                        except TypeError:
                            log_and_print(log_file, '[!] Answer', answer_str, 'is not a float!')
                            log_and_print(log_file, traceback.format_exc())
                            code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                        except Exception:
                            log_and_print(log_file, '[!] Unknown Error!')
                            log_and_print(log_file, traceback.format_exc())
                            code = JUDGE_STATUS.UNKNOWN_ERROR


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

                        command = runner + [datas['executable'], ] + arguments

                        code, stdout, errs = run_cmd(command, datas['cwd'], log_file)

                        if code == JUDGE_STATUS.OK:
                            try:
                                ansfile = open('ans.txt', 'r')
                                answer_str = ansfile.read()
                                if '%' in answer_str:
                                    res = re.findall('(\d+)\.\d+%', answer_str)
                                    if len(res) != 1:
                                        raise ValueError('Cannot find answer in', answer_str)
                                    answer_str = "0." + res[0]
                                else:
                                    res = re.findall('(0\.\d+)', answer_str)
                                    if len(res) != 1:
                                        raise ValueError('Cannot find answer in', answer_str)
                                    answer_str = res[0]
                                answer = float(answer_str)
                                ansfile.close()
                                if answer < 0:
                                    code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                                    log_and_print(log_file, '[!] Answer', answer, 'is a negative value!')
                                else:
                                    datas['score'][datagroup]['dis'][scorepoint] = answer
                                    print()
                            except ValueError:
                                log_and_print(log_file, '[!] Answer', answer_str, 'is not a float!')
                                log_and_print(log_file, traceback.format_exc())
                                code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                            except TypeError:
                                log_and_print(log_file, '[!] Answer', answer_str, 'is not a float!')
                                log_and_print(log_file, traceback.format_exc())
                                code = JUDGE_STATUS.ANSWER_FORMAT_ERROR
                            except Exception:
                                log_and_print(log_file, '[!] Unknown ERROR!')
                                log_and_print(log_file, traceback.format_exc())
                                code = JUDGE_STATUS.UNKNOWN_ERROR

                        if code != JUDGE_STATUS.OK:
                            datas['score'][datagroup]['dis'][scorepoint] = code.value

                        log_and_print(log_file, '[STATUS]', code)
                        log_and_print(log_file, '[STDOUT]', stdout.strip() if stdout else None)
                        log_and_print(log_file, '[STDERR]', errs.strip() if errs else None)
                        log_and_print(log_file, '[ANSWER]', datas['score'][datagroup]['dis'][scorepoint])

        judge_tasks[stuid]['judged'] = True
        result_json.write(json.dumps(judge_tasks[stuid]))
        log_file.close()
        result_json.close()

    open('data.json', 'w').write(json.dumps(judge_tasks))


if __name__ == '__main__':
    print('Load judge points...')
    generate_judge_points()
    print('Load judge tasks...')
    load_judge_tasks()
    do_judge_task()
    exit()

