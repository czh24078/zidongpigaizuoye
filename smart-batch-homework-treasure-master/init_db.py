"""
数据库初始化脚本
用法:
    python init_db.py --host 127.0.0.1 --port 3306 --user root --password xxx --database homework

所有参数可选，缺省从环境变量读取：
    MYSQL_HOST  (默认 127.0.0.1)
    MYSQL_PORT  (默认 3306)
    MYSQL_USER  (默认 root)
    MYSQL_PASSWORD
    MYSQL_DATABASE  (默认 homework)
"""

import argparse
import os
import sys

try:
    import pymysql
except ImportError:
    print("[ERROR] 请先安装 pymysql: pip install pymysql")
    sys.exit(1)

# ── 解析参数 ──────────────────────────────────────────────
parser = argparse.ArgumentParser(description="智能作业批改系统 — 数据库初始化")
parser.add_argument("--host",     default=os.getenv("MYSQL_HOST", "127.0.0.1"))
parser.add_argument("--port",     type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
parser.add_argument("--user",     default=os.getenv("MYSQL_USER", "root"))
parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "homework"))
args = parser.parse_args()

HOST     = args.host
PORT     = args.port
USER     = args.user
PASSWORD = args.password
DATABASE = args.database

# ── 连接 MySQL ────────────────────────────────────────────
def connect_mysql():
    try:
        return pymysql.connect(
            host=HOST, port=PORT, user=USER,
            password=PASSWORD, charset="utf8mb4",
        )
    except pymysql.Error as e:
        print(f"[ERROR] 无法连接 MySQL ({USER}@{HOST}:{PORT}): {e}")
        print("请检查:")
        print("  1. MySQL 服务是否已启动")
        print("  2. 主机 / 端口 / 用户名 / 密码是否正确")
        sys.exit(1)

# ── 开始 ──────────────────────────────────────────────────
print("=" * 50)
print("  智能作业批改系统 — 数据库初始化")
print("=" * 50)
print(f"\n连接信息: {USER}@{HOST}:{PORT}")
print(f"目标库:   {DATABASE}\n")

conn = connect_mysql()
cursor = conn.cursor()

print("[1/3] 创建数据库...")
cursor.execute(
    f"CREATE DATABASE IF NOT EXISTS `{DATABASE}` "
    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
)
conn.commit()
cursor.close()
conn.close()
print(f"  [OK] 数据库 `{DATABASE}` 已就绪")

# ── 建表 ──────────────────────────────────────────────────
conn = pymysql.connect(
    host=HOST, port=PORT, user=USER, password=PASSWORD,
    database=DATABASE, charset="utf8mb4",
)
cursor = conn.cursor()

print("[2/3] 创建表结构...")

TABLES = [
    # exams
    (
        "exams",
        """
        CREATE TABLE IF NOT EXISTS `exams` (
            `id`         VARCHAR(36)  NOT NULL,
            `filename`   VARCHAR(500) NOT NULL,
            `source`     VARCHAR(20)  NOT NULL,
            `created_at` DATETIME     NOT NULL,
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    # questions
    (
        "questions",
        """
        CREATE TABLE IF NOT EXISTS `questions` (
            `id`              INT         NOT NULL AUTO_INCREMENT,
            `exam_id`         VARCHAR(36) NOT NULL,
            `question_no`     VARCHAR(50) NOT NULL,
            `question_text`   TEXT        NOT NULL,
            `standard_answer` TEXT        NOT NULL,
            `options`         TEXT        NULL,
            `analysis`        TEXT        NULL,
            PRIMARY KEY (`id`),
            INDEX (`exam_id`),
            CONSTRAINT `fk_questions_exam` FOREIGN KEY (`exam_id`)
                REFERENCES `exams` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    # corrections
    (
        "corrections",
        """
        CREATE TABLE IF NOT EXISTS `corrections` (
            `id`          VARCHAR(36)  NOT NULL,
            `filename`    VARCHAR(500) NOT NULL,
            `result`      TEXT         NULL,
            `score`       INT          NULL,
            `summary`     VARCHAR(500) NULL,
            `exam_id`     VARCHAR(36)  NULL,
            `record_path` VARCHAR(500) NULL,
            `created_at`  DATETIME     NOT NULL,
            PRIMARY KEY (`id`),
            INDEX (`exam_id`),
            CONSTRAINT `fk_corrections_exam` FOREIGN KEY (`exam_id`)
                REFERENCES `exams` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    # correction_details
    (
        "correction_details",
        """
        CREATE TABLE IF NOT EXISTS `correction_details` (
            `id`              INT         NOT NULL AUTO_INCREMENT,
            `correction_id`   VARCHAR(36) NOT NULL,
            `question_no`     VARCHAR(50) NOT NULL,
            `question_text`   TEXT        NOT NULL,
            `student_answer`  TEXT        NOT NULL,
            `standard_answer` TEXT        NOT NULL,
            `is_correct`      TINYINT(1)  NOT NULL,
            `score`           FLOAT       NULL,
            `full_score`      FLOAT       NULL,
            `analysis`        TEXT        NOT NULL,
            PRIMARY KEY (`id`),
            INDEX (`correction_id`),
            CONSTRAINT `fk_detail_correction` FOREIGN KEY (`correction_id`)
                REFERENCES `corrections` (`id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    # question_bank
    (
        "question_bank",
        """
        CREATE TABLE IF NOT EXISTS `question_bank` (
            `id`              INT          NOT NULL AUTO_INCREMENT,
            `exam_id`         VARCHAR(36)  NULL,
            `question_no`     VARCHAR(50)  NOT NULL,
            `question_text`   TEXT         NOT NULL,
            `standard_answer` TEXT         NOT NULL,
            `analysis`        TEXT         NULL,
            `exam_filename`   VARCHAR(500) NOT NULL,
            `bank_no`         INT          NULL,
            `added_at`        DATETIME     NOT NULL,
            PRIMARY KEY (`id`),
            INDEX (`exam_id`),
            CONSTRAINT `fk_bank_exam` FOREIGN KEY (`exam_id`)
                REFERENCES `exams` (`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
]

for name, sql in TABLES:
    cursor.execute(sql)
    print(f"  [OK] `{name}`")

conn.commit()

# ── 预置题库 ──────────────────────────────────────────────
print("[3/3] 写入预置题库数据...")
cursor.execute("SELECT COUNT(*) FROM question_bank")
if cursor.fetchone()[0] > 0:
    print("  [SKIP] 题库已有数据，跳过写入")
else:
    seeds = [
        (8, None, '1',
         '阅读下面的古诗，回答问题。\n\n《春夜洛城闻笛》\n李白\n谁家玉笛暗飞声，散入春风满洛城。\n此夜曲中闻折柳，何人不起故园情。\n\n（1）请写出诗中运用了比喻修辞手法的一句，并说明其作用。\n（2）\'折柳\'在古诗中常用来表达什么情感？结合全诗分析诗人的情感。',
         '（1）\'散入春风满洛城\'运用了比喻，将笛声比作随春风飘散的细雨或轻烟，形象地表现了笛声无处不在、弥漫全城的特点，增强了听觉感受的感染力。（2）\'折柳\'是古代送别时的习俗，象征离别之情。本诗通过\'闻折柳\'引发对故乡的思念，表达了诗人深切的思乡之情。',
         '本题考查古诗文鉴赏能力，包括修辞手法识别与情感分析。学生需理解诗句意象并结合文化背景进行解读。',
         'AI生成题目', 1, '2026-05-24 18:19:51'),
        (9, None, '2',
         '下列句子中没有语病的一项是（　　）\nA. 通过这次活动，使我明白了团结的重要性。\nB. 同学们认真地讨论并听取了老师的建议。\nC. 我们要发扬和继承中华民族的优良传统。\nD. 这本书的内容丰富，插图也十分精美。',
         'D',
         'A项缺主语，\'通过……使……\'导致主语缺失；B项语序不当，应为\'听取并讨论\'；C项逻辑顺序错误，应先\'继承\'后\'发扬\'；D项无语病，结构完整，搭配合理。',
         'AI生成题目', 2, '2026-05-24 18:19:57'),
        (10, None, '3',
         '请将下列句子改为反问句：\n这幅画真美，让人忍不住驻足欣赏。',
         '这幅画真美，难道不让人忍不住驻足欣赏吗？',
         '本题考查句式转换能力。将陈述句转为反问句时，需添加反问语气词\'难道\'和疑问助词\'吗\'，同时将肯定语气变为否定形式以增强语气。',
         'AI生成题目', 3, '2026-05-24 18:19:58'),
        (11, None, '5',
         '从下列成语中选择一个填入横线处，使句子通顺且符合语境：\n他虽然年纪小，但做事一丝不苟，真是__________。\n备选成语：鹤立鸡群、精益求精、见多识广、一鸣惊人',
         '精益求精',
         '\'精益求精\'指在已经很好的基础上追求更加完美，符合\'做事一丝不苟\'的语境。其他选项如\'鹤立鸡群\'强调出众，\'见多识广\'强调阅历，\'一鸣惊人\'强调突然出名，均不如\'精益求精\'贴切。',
         'AI生成题目', 4, '2026-05-24 18:20:00'),
        (12, None, '4',
         '阅读下面文言文片段，回答问题。\n\n陈太丘与友期行，期日中。过中不至，太丘舍去，去后乃至。元方时年七岁，门外戏。客问元方：\'尊君在不？\'答曰：\'待君久不至，已去。\'友人便怒曰：\'非人哉！与人期行，相委而去。\'元方曰：\'君与家君期日中。日中不至，则是无信；对子骂父，则是无礼。\'友人惭，下车引之。元方入门不顾。\n\n（1）解释加点字：\'期\'、\'顾\'。\n（2）用现代汉语翻译画线句：\'日中不至，则是无信；对子骂父，则是无礼。\'',
         '（1）期：约定；顾：回头看。\n（2）正午时分不到，就是没有信用；当着孩子的面骂他的父亲，就是没有礼貌。',
         '本题考查文言实词理解和句子翻译能力。\'期\'为动词\'约定\'，\'顾\'在此处指\'回头看\'。翻译时需准确传达原意，注意\'则\'表示因果关系。',
         'AI生成题目', 5, '2026-05-24 18:20:01'),
    ]
    cursor.executemany(
        "INSERT INTO question_bank "
        "(id, exam_id, question_no, question_text, standard_answer, analysis, exam_filename, bank_no, added_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        seeds,
    )
    conn.commit()
    print(f"  [OK] 已写入 {len(seeds)} 条预置题目")

# ── 验证 ──────────────────────────────────────────────────
cursor.execute("SHOW TABLES")
tables = [t[0] for t in cursor.fetchall()]
cursor.execute("SELECT COUNT(*) FROM question_bank")
bank_count = cursor.fetchone()[0]

print(f"\n{'=' * 50}")
print(f"  数据库初始化完成！")
print(f"  库名:   {DATABASE}")
print(f"  表数量: {len(tables)} — {', '.join(tables)}")
print(f"  题库:   {bank_count} 条预置题目")
print(f"{'=' * 50}")

cursor.close()
conn.close()
