# AutoJudger

采用文件输入输出方式，直接运行可执行文件的自动评测机，实现自动读取数据点，自动解析待评测的任务，并输出评测结果到json和记录日志到log。要求python版本3.7.8

## Data Config

配置数据时，每个数据组的文件夹需以`sim_name`命名，`name`在程序中作为数组组的唯一标识，不得重复

然后在`data_dict`中进行相应配置，写下大测试组的名字`name`

每个数据组下存放数据测试点文件，例如在本次的论文查重作业中，`orig.txt`是原文文件，每个测试点需以`orig_name_operation(_id).txt`命名，`operation`决定给测试点唯一标识，`id`是当此测试点有多个测试时，用`id`加以区分

```python
{
    '0.7': {
        'orig': 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_orig.txt',
        'add': 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_add.txt',
        'del': 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_del.txt',
        'dis': {1: 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_dis_1.txt', 10: 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_dis_10.txt', 15: 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_dis_15.txt', 3: 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_dis_3.txt', 7: 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_dis_7.txt'},
        'mix': 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_mix.txt',
        'rep': 'E:\\Python\\Projects\\AutoJudger\\data\\sim_0.7\\orig_0.7_rep.txt'
    },
    '0.9':  {
        # ...
    }
}
```

自动评测器运行时先经过`generate_judge_points()`函数生成如上所示的测试点数据和每个学生的测试结果的结构`score_structure`（如下）：

```python
{
    '0.7': {
        'add': None, 
        'del': None,
        'dis': {1: None, 10: None, 15: None, 3: None, 7: None},
        'mix': None,
        'orig': None,
        'rep': None
    },
    '0.9': {
      # ...
    }
}
```

# Judge Task

评测任务是以学生的程序的单位，在每个评测任务中，记录了评测任务的工作目录、可执行程序，评测器将遍历所有评测任务，对于每个评测任务评测所有的测试点并记录结果

配置评测任务时，需在`judge_runner`配置不同种类的评测任务（例如`.py`/`.exe`/`.jar`）的执行器`Runner`

加载评测任务时，调用`load_judge_tasks()`，在`src`中以学号命名的文件夹中遍历，以`main`为文件名的且其扩展名(如`.py`)存在于执行器的有效配置中将被作为评测任务的可执行程序`executable`，工作目录`cwd`为学生提交的学号命名的文件夹

若当前文件夹下没有可执行文件，程序会在控制台中输出警告信息，扫描完毕后与学生名单`studentlist`作差集运算，找出未交作业或作业无效的学生名单并输出

# Do Judge

评测采取逐个评测的方式，同一时间只有一个评测任务的其中一个评测点在运行，开始评测任务时创建的线程是用于检测内存占用，将在评测器创建的子进程内存占用超出指定限制时杀死该评测点的评测进程

对于每个评测点，规定了如下几种评测状态，每个评测状态对应一个数字：

* OK
* CRASH
* TIMEOUT
* UNKNOWN_ERROR
* ANSWER_FORMAT_ERROR

其中CRASH状态也可能由进程内存占用超过限制被杀死导致，也可能是进程异常退出或者执行器Runner无法执行该进程，或是执行器Runner加载失败

若超过一定的时间进程依然没有退出，评测器将杀死评测点进程并标记该评测点为超时状态，不论最后是否输出了答案！

在进程正常退出，向答案文件输出了数据之后，评测器会读取答案文件，并尝试加载答案，若答案格式不正确或者无法加载，评测点状态将被标记为`ANSWER_FORMAT_ERROR`。

出现`UNKNOWN_ERROR`时，往往需要评测组的同学手动查看日志，并进行手动评测来断定是评测器导致的错误还是对方程序编写的不正确导致的错误

当评测点的结果为负值时，表示评测失败（失败原因请将负值取个绝对值再对应到评测状态），为正数的均是评测成功的测试点

评测结果将以`generate_judge_points()`生成的测试结果结构`score_structure`进行组织。

运行时输出的STDOUT、STDERR信息也将一同记录在log文件中，`logs`文件夹和`results`文件夹分别存放了每个学生的评测日志和评测结果

## Generate Score

所有评测任务评测完毕之后，要做到事情就是根据评测结果生成得分，在这次的评测中，`0.7`表示替换了30%的文本，`0.9`表示替换了10%的文本：

* 显然按照平行的比较关系，前者的重复率答案要大于后者，例如`0.7_add > 0.9_add`
* 将原文作为“抄袭版”论文的测试点，必须重复率为`1.00`
* `dis`数据组中评测结果必须和`id`呈现单调递减关系

如上每个不满足，扣2分，若测试点没有通过测试（评测失败），也是一个点扣2分，最后生成`score.json`进行记录。