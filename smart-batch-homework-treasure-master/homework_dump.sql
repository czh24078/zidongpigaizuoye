-- MySQL dump 10.13  Distrib 8.4.9, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: homework
-- ------------------------------------------------------
-- Server version	8.4.9

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `correction_details`
--

DROP TABLE IF EXISTS `correction_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `correction_details` (
  `id` int NOT NULL AUTO_INCREMENT,
  `correction_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_answer` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `standard_answer` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_correct` tinyint(1) NOT NULL,
  `score` float DEFAULT NULL,
  `full_score` float DEFAULT NULL,
  `analysis` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `correction_id` (`correction_id`),
  CONSTRAINT `correction_details_ibfk_1` FOREIGN KEY (`correction_id`) REFERENCES `corrections` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `correction_details`
--

LOCK TABLES `correction_details` WRITE;
/*!40000 ALTER TABLE `correction_details` DISABLE KEYS */;
/*!40000 ALTER TABLE `correction_details` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `corrections`
--

DROP TABLE IF EXISTS `corrections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `corrections` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `filename` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result` text COLLATE utf8mb4_unicode_ci,
  `score` int DEFAULT NULL,
  `summary` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `exam_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `record_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `exam_id` (`exam_id`),
  CONSTRAINT `corrections_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `corrections`
--

LOCK TABLES `corrections` WRITE;
/*!40000 ALTER TABLE `corrections` DISABLE KEYS */;
/*!40000 ALTER TABLE `corrections` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `exams`
--

DROP TABLE IF EXISTS `exams`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `exams` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `filename` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `exams`
--

LOCK TABLES `exams` WRITE;
/*!40000 ALTER TABLE `exams` DISABLE KEYS */;
/*!40000 ALTER TABLE `exams` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `question_bank`
--

DROP TABLE IF EXISTS `question_bank`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `question_bank` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `question_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `standard_answer` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `analysis` text COLLATE utf8mb4_unicode_ci,
  `exam_filename` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bank_no` int DEFAULT NULL,
  `added_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `question_bank_ibfk_1` (`exam_id`),
  CONSTRAINT `question_bank_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `question_bank`
--

LOCK TABLES `question_bank` WRITE;
/*!40000 ALTER TABLE `question_bank` DISABLE KEYS */;
INSERT INTO `question_bank` VALUES (8,NULL,'1','阅读下面的古诗，回答问题。\n\n《春夜洛城闻笛》\n李白\n谁家玉笛暗飞声，散入春风满洛城。\n此夜曲中闻折柳，何人不起故园情。\n\n（1）请写出诗中运用了比喻修辞手法的一句，并说明其作用。\n（2）‘折柳’在古诗中常用来表达什么情感？结合全诗分析诗人的情感。','（1）‘散入春风满洛城’运用了比喻，将笛声比作随春风飘散的细雨或轻烟，形象地表现了笛声无处不在、弥漫全城的特点，增强了听觉感受的感染力。（2）‘折柳’是古代送别时的习俗，象征离别之情。本诗通过‘闻折柳’引发对故乡的思念，表达了诗人深切的思乡之情。','本题考查古诗文鉴赏能力，包括修辞手法识别与情感分析。学生需理解诗句意象并结合文化背景进行解读。','AI生成题目',1,'2026-05-24 18:19:51'),(9,NULL,'2','下列句子中没有语病的一项是（　　）\nA. 通过这次活动，使我明白了团结的重要性。\nB. 同学们认真地讨论并听取了老师的建议。\nC. 我们要发扬和继承中华民族的优良传统。\nD. 这本书的内容丰富，插图也十分精美。','D','A项缺主语，‘通过……使……’导致主语缺失；B项语序不当，应为‘听取并讨论’；C项逻辑顺序错误，应先‘继承’后‘发扬’；D项无语病，结构完整，搭配合理。','AI生成题目',2,'2026-05-24 18:19:57'),(10,NULL,'3','请将下列句子改为反问句：\n这幅画真美，让人忍不住驻足欣赏。','这幅画真美，难道不让人忍不住驻足欣赏吗？','本题考查句式转换能力。将陈述句转为反问句时，需添加反问语气词‘难道’和疑问助词‘吗’，同时将肯定语气变为否定形式以增强语气。','AI生成题目',3,'2026-05-24 18:19:58'),(11,NULL,'5','从下列成语中选择一个填入横线处，使句子通顺且符合语境：\n他虽然年纪小，但做事一丝不苟，真是__________。\n备选成语：鹤立鸡群、精益求精、见多识广、一鸣惊人','精益求精','‘精益求精’指在已经很好的基础上追求更加完美，符合‘做事一丝不苟’的语境。其他选项如‘鹤立鸡群’强调出众，‘见多识广’强调阅历，‘一鸣惊人’强调突然出名，均不如‘精益求精’贴切。','AI生成题目',4,'2026-05-24 18:20:00'),(12,NULL,'4','阅读下面文言文片段，回答问题。\n\n陈太丘与友期行，期日中。过中不至，太丘舍去，去后乃至。元方时年七岁，门外戏。客问元方：‘尊君在不？’答曰：‘待君久不至，已去。’友人便怒曰：‘非人哉！与人期行，相委而去。’元方曰：‘君与家君期日中。日中不至，则是无信；对子骂父，则是无礼。’友人惭，下车引之。元方入门不顾。\n\n（1）解释加点字：‘期’、‘顾’。\n（2）用现代汉语翻译画线句：‘日中不至，则是无信；对子骂父，则是无礼。’','（1）期：约定；顾：回头看。\n（2）正午时分不到，就是没有信用；当着孩子的面骂他的父亲，就是没有礼貌。','本题考查文言实词理解和句子翻译能力。‘期’为动词‘约定’，‘顾’在此处指‘回头看’。翻译时需准确传达原意，注意‘则’表示因果关系。','AI生成题目',5,'2026-05-24 18:20:01');
/*!40000 ALTER TABLE `question_bank` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `questions`
--

DROP TABLE IF EXISTS `questions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `questions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `standard_answer` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `options` text COLLATE utf8mb4_unicode_ci,
  `analysis` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  KEY `exam_id` (`exam_id`),
  CONSTRAINT `questions_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `questions`
--

LOCK TABLES `questions` WRITE;
/*!40000 ALTER TABLE `questions` DISABLE KEYS */;
/*!40000 ALTER TABLE `questions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'homework'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-24 18:25:26
