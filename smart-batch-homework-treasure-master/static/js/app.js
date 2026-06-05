const { createApp, ref, reactive, computed, onMounted } = Vue;

const app = createApp({
    setup() {
        // ==================== 状态 ====================
        const uploadFiles = ref([]);
        const previewUrls = ref([]);
        const correctionResult = ref('');
        const isLoading = ref(false);
        const isStreaming = ref(false);
        const history = ref([]);
        const isDragOver = ref(false);
        const fileInput = ref(null);

        // 试题相关状态
        const exams = ref([]);
        const selectedExamId = ref('');
        const isExamUploading = ref(false);
        const examFileInput = ref(null);
        const answerEditorVisible = ref(false);
        const editingQuestions = ref([]);
        const isSavingAnswers = ref(false);
        const isDeletingExam = ref(false);

        // 导航栏状态
        const activeNav = ref('home');

        // 历史题目查看状态
        const questionDetailVisible = ref(false);
        const viewingQuestion = ref(null);

        // 题库（MySQL 持久化）
        const questionBank = ref([]);

        // 搜索状态
        const historyKeyword = ref('');
        const bankQuestionNo = ref('');
        const bankKeyword = ref('');

        // 分页状态
        const examPage = ref(1);
        const examTotal = ref(0);
        const examPageSize = ref(20);
        const historyPage = ref(1);
        const historyTotal = ref(0);
        const historyPageSize = ref(20);
        const bankPage = ref(1);
        const bankTotal = ref(0);
        const bankPageSize = ref(20);
        const allBankQuestions = ref([]);

        async function fetchQuestionBank() {
            try {
                const params = { page: bankPage.value, page_size: bankPageSize.value };
                if (bankKeyword.value) params.keyword = bankKeyword.value;
                if (bankQuestionNo.value) params.question_no = bankQuestionNo.value;
                const resp = await axios.get('/api/question-bank', { params });
                const data = resp.data;
                questionBank.value = Array.isArray(data) ? data : (data.items || []);
                bankTotal.value = data.total || 0;
            } catch { questionBank.value = []; bankTotal.value = 0; }
        }

        // 试卷生成状态
        const examPaperSubject = ref('不限');
        const examPaperCount = ref(5);
        const examPaperQuestions = ref([]);

        // AI 服务状态
        const aiAvailable = ref(true);

        // AI 出题状态
        const aiGeneratedQuestions = ref([]);
        const aiForm = reactive({ subject: '语文', grade: '初中', difficulty: '中等', count: 5, requirement: '' });
        const isGenerating = ref(false);
        let abortController = null;
        const addedGeneratedKeys = reactive(new Set());

        // 将所有试卷的题目展平为单题列表
        const allQuestions = computed(() => {
            const list = [];
            for (const exam of exams.value) {
                for (const q of exam.questions) {
                    list.push({
                        ...q,
                        examId: exam.id,
                        examFilename: exam.filename,
                        examCreatedAt: exam.created_at
                    });
                }
            }
            return list;
        });

        // 文件限制配置
        const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
        const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

        // ==================== 计算属性 ====================
        const renderedResult = computed(() => {
            if (!correctionResult.value) return '';
            return renderMarkdown(correctionResult.value);
        });

        const currentExam = computed(() => {
            if (!selectedExamId.value) return null;
            return exams.value.find(e => e.id === selectedExamId.value) || null;
        });

        // 历史题目筛选
        const filteredQuestions = computed(() => {
            let list = allQuestions.value;
            const kw = historyKeyword.value.trim().toLowerCase();
            if (kw) {
                list = list
                    .map(q => {
                        const text = (q.question_text || '').toLowerCase();
                        const answer = (q.standard_answer || '').toLowerCase();
                        const count = (text.match(new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length
                                    + (answer.match(new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length;
                        return { ...q, _matchCount: count };
                    })
                    .filter(q => q._matchCount > 0)
                    .sort((a, b) => {
                        const dc = b._matchCount - a._matchCount;
                        if (dc !== 0) return dc;
                        return (b.examCreatedAt || '').localeCompare(a.examCreatedAt || '');
                    });
            }
            return list;
        });

        // 题库筛选
        const filteredBank = computed(() => {
            let list = questionBank.value;
            if (bankQuestionNo.value.trim()) {
                const no = parseInt(bankQuestionNo.value.trim(), 10);
                if (!isNaN(no)) {
                    list = list.filter(q => q.bank_no === no);
                }
            }
            if (bankKeyword.value.trim()) {
                const kw = bankKeyword.value.trim().toLowerCase();
                list = list.filter(q =>
                    (q.question_text || '').toLowerCase().includes(kw) ||
                    (q.standard_answer || '').toLowerCase().includes(kw) ||
                    (q.analysis || '').toLowerCase().includes(kw)
                );
            }
            return list;
        });

        const examPaperAvailableCount = computed(() => {
            if (examPaperSubject.value === '不限') return allBankQuestions.value.length;
            return allBankQuestions.value.filter(q => q.subject === examPaperSubject.value).length;
        });

        // ==================== 工具方法 ====================

        /**
         * 显示消息提示
         */
        function showMessage(message, type = 'info') {
            ElementPlus.ElMessage({
                message,
                type,
                duration: 3000,
                showClose: true
            });
        }

        /**
         * 验证文件
         */
        function validateFile(file) {
            if (!ALLOWED_TYPES.includes(file.type)) {
                showMessage(`文件 "${file.name}" 格式不支持，仅接受 JPG、PNG、WebP 格式`, 'warning');
                return false;
            }
            if (file.size > MAX_FILE_SIZE) {
                showMessage(`文件 "${file.name}" 超过 10MB 大小限制`, 'warning');
                return false;
            }
            return true;
        }

        /**
         * 添加文件到列表
         */
        function addFiles(files) {
            const validFiles = [];
            const validPreviews = [];

            for (const file of files) {
                if (validateFile(file)) {
                    validFiles.push(file);
                    validPreviews.push(URL.createObjectURL(file));
                }
            }

            if (validFiles.length > 0) {
                uploadFiles.value.push(...validFiles);
                previewUrls.value.push(...validPreviews);
                showMessage(`成功添加 ${validFiles.length} 张图片`, 'success');
            }
        }

        // ==================== 上传相关方法 ====================

        /**
         * 触发文件选择
         */
        function triggerFileInput() {
            if (fileInput.value) {
                fileInput.value.click();
            }
        }

        /**
         * 文件选择处理
         */
        function handleFileSelect(event) {
            const files = event.target.files;
            if (files && files.length > 0) {
                addFiles(Array.from(files));
            }
            // 重置 input 以便重复选择相同文件
            event.target.value = '';
        }

        /**
         * 拖拽进入
         */
        function handleDragOver(event) {
            event.preventDefault();
            isDragOver.value = true;
        }

        /**
         * 拖拽离开
         */
        function handleDragLeave(event) {
            event.preventDefault();
            isDragOver.value = false;
        }

        /**
         * 拖拽放下
         */
        function handleDrop(event) {
            event.preventDefault();
            isDragOver.value = false;
            const files = event.dataTransfer.files;
            if (files && files.length > 0) {
                addFiles(Array.from(files));
            }
        }

        /**
         * 移除已选文件
         */
        function removeFile(index) {
            if (index >= 0 && index < uploadFiles.value.length) {
                URL.revokeObjectURL(previewUrls.value[index]);
                uploadFiles.value.splice(index, 1);
                previewUrls.value.splice(index, 1);
            }
        }

        /**
         * 清空所有文件
         */
        function clearAllFiles() {
            previewUrls.value.forEach(url => URL.revokeObjectURL(url));
            uploadFiles.value = [];
            previewUrls.value = [];
        }

        // ==================== 批改提交方法 ====================

        /**
         * 提交批改（普通模式）
         */
        async function submitCorrection() {
            if (uploadFiles.value.length === 0) {
                showMessage('请先上传图片', 'warning');
                return;
            }

            isLoading.value = true;
            isStreaming.value = false;
            correctionResult.value = '';

            const formData = new FormData();
            formData.append('file', uploadFiles.value[0]);
            if (selectedExamId.value) {
                formData.append('exam_id', selectedExamId.value);
            }

            try {
                const response = await axios.post('/api/correct', formData, {
                    headers: {
                        'Content-Type': 'multipart/form-data'
                    },
                    timeout: 120000 // 2分钟超时
                });

                if (response.data && response.data.result) {
                    correctionResult.value = response.data.result;
                    showMessage('批改完成', 'success');
                } else if (response.data && typeof response.data === 'string') {
                    correctionResult.value = response.data;
                    showMessage('批改完成', 'success');
                } else {
                    correctionResult.value = JSON.stringify(response.data, null, 2);
                    showMessage('批改完成', 'success');
                }

                // 刷新历史记录、试题列表和题库
                await fetchHistory();
                await fetchExams();
                await fetchQuestionBank();
            } catch (error) {
                console.error('批改请求失败:', error);
                const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message || '批改请求失败，请稍后重试';
                showMessage(errorMsg, 'error');
            } finally {
                isLoading.value = false;
            }
        }

        /**
         * 提交批改（流式输出模式）
         */
        async function submitCorrectionStream() {
            if (uploadFiles.value.length === 0) {
                showMessage('请先上传图片', 'warning');
                return;
            }

            isLoading.value = true;
            isStreaming.value = true;
            correctionResult.value = '';

            const formData = new FormData();
            formData.append('file', uploadFiles.value[0]);
            if (selectedExamId.value) {
                formData.append('exam_id', selectedExamId.value);
            }

            try {
                const response = await fetch('/api/correct/stream', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || '流式请求失败');
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.slice(6).trim();
                            if (!dataStr) continue;

                            try {
                                const data = JSON.parse(dataStr);

                                if (data.event === 'start') {
                                    console.log('开始批改:', data.message);
                                    showMessage(data.message, 'info');
                                } else if (data.event === 'progress') {
                                    showMessage(data.message, 'info');
                                } else if (data.event === 'content') {
                                    correctionResult.value += data.text;
                                } else if (data.event === 'result') {
                                    if (correctionResult.value && !correctionResult.value.endsWith('\n\n')) {
                                        correctionResult.value += '\n\n';
                                    }
                                    correctionResult.value += `### ${data.section || ''}\n- **得分**: ${data.score || '-'}\n- **详情**: ${data.detail || ''}\n\n`;
                                } else if (data.event === 'summary') {
                                    correctionResult.value += `\n\n---\n\n## 总结\n\n${data.message || ''}`;
                                } else if (data.event === 'final_text') {
                                    correctionResult.value = data.text;
                                } else if (data.event === 'end') {
                                    showMessage('批改完成', 'success');
                                    await fetchHistory();
                                    await fetchExams();
                                    await fetchQuestionBank();
                                }
                            } catch (e) {
                                console.error('解析流式数据失败:', e, dataStr);
                            }
                        }
                    }
                }
            } catch (error) {
                console.error('流式批改失败:', error);
                showMessage(error.message || '流式批改失败，请稍后重试', 'error');
            } finally {
                isLoading.value = false;
                isStreaming.value = false;
            }
        }

        // ==================== 历史记录方法 ====================

        /**
         * 获取批改历史
         */
        async function fetchHistory() {
            try {
                const response = await axios.get('/api/history', {
                    params: { page: historyPage.value, page_size: historyPageSize.value },
                    timeout: 30000
                });
                const data = response.data;
                history.value = Array.isArray(data) ? data : (data.items || []);
                historyTotal.value = data.total || 0;
            } catch (error) {
                console.error('获取历史记录失败:', error);
                history.value = [];
                historyTotal.value = 0;
            }
        }

        /**
         * 查看历史详情
         */
        function viewHistoryDetail(item) {
            if (item.result) {
                correctionResult.value = item.result;
                showMessage('已加载历史记录详情', 'success');
                // 滚动到结果区域
                setTimeout(() => {
                    const resultCard = document.querySelector('.result-card');
                    if (resultCard) {
                        resultCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 100);
            } else {
                showMessage('该记录暂无详细结果', 'warning');
            }
        }

        /**
         * 根据分数获取标签类型
         */
        function getScoreTagType(score) {
            if (score >= 90) return 'success';
            if (score >= 75) return 'primary';
            if (score >= 60) return 'warning';
            return 'danger';
        }

        function getSubjectTagType(subject) {
            const map = { '语文': '', '数学': 'success', '物理': 'warning', '历史': 'danger' };
            return map[subject] || 'info';
        }

        // ==================== Markdown 渲染 ====================

        /**
         * 清理文本中的 JSON 结构化数据残留
         */
        function cleanJsonArtifacts(text) {
            if (!text) return text;
            let cleaned = text;
            // 1. 移除 ```json ... ``` 代码块
            cleaned = cleaned.replace(/```json[\s\S]*?```/g, '');
            cleaned = cleaned.replace(/```[\s\S]*?```/g, '');
            // 2. 移除末尾的 JSON 数组 [...]
            cleaned = cleaned.replace(/\n*\s*\[\s*\{\s*"question_no"[\s\S]*$/g, '');
            // 3. 移除末尾的 JSON 对象 {...}
            cleaned = cleaned.replace(/\n*\s*\{\s*"total_score"[\s\S]*$/g, '');
            // 4. 清理多余的连续空行
            cleaned = cleaned.replace(/\n{4,}/g, '\n\n\n');
            return cleaned.trim();
        }

        /**
         * 使用 marked 渲染 Markdown
         */
        function renderMarkdown(text) {
            if (!text) return '';
            try {
                // 配置 marked
                marked.setOptions({
                    breaks: true,
                    gfm: true,
                    headerIds: false,
                    mangle: false
                });
                return marked.parse(cleanJsonArtifacts(text));
            } catch (error) {
                console.error('Markdown 渲染失败:', error);
                return `<pre>${escapeHtml(text)}</pre>`;
            }
        }

        /**
         * HTML 转义
         */
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // ==================== 试题管理 ====================

        function triggerExamFileInput() {
            if (examFileInput.value) examFileInput.value.click();
        }

        async function handleExamFileSelect(event) {
            const files = event.target.files ? Array.from(event.target.files) : [];
            event.target.value = '';
            if (files.length === 0) return;

            const validFiles = files.filter(validateFile);
            if (validFiles.length === 0) return;

            isExamUploading.value = true;
            try {
                const fd = new FormData();
                validFiles.forEach(f => fd.append('files', f));
                const resp = await axios.post('/api/exam/upload', fd, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                    timeout: 180000
                });
                showMessage(resp.data.message || `试题识别完成，已导入题库`, 'success');
                await fetchQuestionBank();
            } catch (error) {
                console.error(error);
                const msg = error.response?.data?.detail || error.message || '试题上传失败';
                showMessage(msg, 'error');
            } finally {
                isExamUploading.value = false;
            }
        }

        async function fetchExams() {
            try {
                const params = { page: examPage.value, page_size: examPageSize.value };
                if (historyKeyword.value) params.keyword = historyKeyword.value;
                const resp = await axios.get('/api/exams', { params });
                const data = resp.data;
                exams.value = Array.isArray(data) ? data : (data.items || []);
                examTotal.value = data.total || 0;
            } catch (error) {
                console.error(error);
                exams.value = [];
                examTotal.value = 0;
            }
        }

        // ==================== 历史题目 ====================

        function viewQuestionDetail(q) {
            viewingQuestion.value = q;
            questionDetailVisible.value = true;
        }

        // ==================== 题库 ====================

        function clearBankSearch() {
            bankQuestionNo.value = '';
            bankKeyword.value = '';
        }

        function highlightKeyword(text) {
            const kw = (activeNav.value === 'exam-history' ? historyKeyword.value : bankKeyword.value).trim();
            if (!kw || !text) return text;
            const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(`(${escaped})`, 'gi');
            return text.replace(regex, '<mark>$1</mark>');
        }

        // ==================== 题库 ====================

        function isInBank(q) {
            return questionBank.value.some(
                b => b.exam_id === q.examId && b.question_no === q.question_no
            );
        }

        async function addToBank(q) {
            if (isInBank(q)) {
                showMessage('该题目已在题库中', 'warning');
                return;
            }
            try {
                await axios.post('/api/question-bank', {
                    exam_id: q.examId,
                    question_no: q.question_no,
                    question_text: q.question_text,
                    standard_answer: q.standard_answer,
                    analysis: q.analysis,
                    exam_filename: q.examFilename,
                    subject: q.subject || '其他'
                });
                await fetchQuestionBank();
                showMessage('已加入题库', 'success');
            } catch(e) {
                const msg = e.response?.data?.detail || e.message;
                showMessage('添加失败: ' + msg, 'error');
            }
        }

        async function removeFromBank(itemId) {
            try {
                await axios.delete(`/api/question-bank/${itemId}`);
                await fetchQuestionBank();
                showMessage('已从题库移除', 'success');
            } catch(e) {
                showMessage('移除失败', 'error');
            }
        }

        function clearBank() {
            ElementPlus.ElMessageBox.confirm(
                '确定要清空题库吗？',
                '确认清空',
                { confirmButtonText: '清空', cancelButtonText: '取消', type: 'warning' }
            ).then(async () => {
                try {
                    await axios.delete('/api/question-bank');
                    questionBank.value = [];
                    showMessage('题库已清空', 'success');
                } catch(e) {
                    showMessage('清空失败', 'error');
                }
            }).catch(() => {});
        }

        // ==================== 试卷生成 ====================

        function shuffleArray(arr) {
            const a = [...arr];
            for (let i = a.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [a[i], a[j]] = [a[j], a[i]];
            }
            return a;
        }

        async function fetchAllBankQuestions() {
            try {
                const resp = await axios.get('/api/question-bank/all');
                allBankQuestions.value = Array.isArray(resp.data) ? resp.data : [];
            } catch { allBankQuestions.value = []; }
        }

        async function generateExamPaper() {
            // 先刷新全量题库再出题
            await fetchAllBankQuestions();
            if (allBankQuestions.value.length === 0) {
                showMessage('题库为空，请先添加题目', 'warning');
                return;
            }
            let pool = allBankQuestions.value;
            if (examPaperSubject.value !== '不限') {
                pool = pool.filter(q => q.subject === examPaperSubject.value);
                if (pool.length === 0) {
                    showMessage(`题库中没有"${examPaperSubject.value}"科目的题目`, 'warning');
                    return;
                }
            }
            const count = Math.min(examPaperCount.value, pool.length);
            examPaperQuestions.value = shuffleArray(pool).slice(0, count);
        }

        function clearExamPaper() {
            examPaperQuestions.value = [];
        }

        async function downloadExamPaper() {
            if (examPaperQuestions.value.length === 0) return;
            try {
                const payload = examPaperQuestions.value.map(q => ({
                    question_no: q.question_no,
                    question_text: q.question_text,
                    standard_answer: q.standard_answer,
                    analysis: q.analysis || ''
                }));
                const resp = await axios.post('/api/exam-paper/export', payload, {
                    responseType: 'blob'
                });
                const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const now = new Date();
                const ts = now.getFullYear() + String(now.getMonth()+1).padStart(2,'0') + String(now.getDate()).padStart(2,'0') + '_' + String(now.getHours()).padStart(2,'0') + String(now.getMinutes()).padStart(2,'0') + String(now.getSeconds()).padStart(2,'0');
                a.download = `练习试卷_${ts}.docx`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showMessage('试卷已下载', 'success');
            } catch (error) {
                console.error('导出试卷失败:', error);
                showMessage('导出试卷失败', 'error');
            }
        }

        // ==================== AI 出题 ====================

        async function generateQuestions() {
            if (isGenerating.value) return;
            isGenerating.value = true;
            aiGeneratedQuestions.value = [];
            addedGeneratedKeys.clear();
            abortController = new AbortController();
            try {
                const resp = await axios.post('/api/ai-generate', {
                    subject: aiForm.subject,
                    grade: aiForm.grade,
                    question_type: '混合',
                    difficulty: aiForm.difficulty,
                    count: aiForm.count,
                    requirement: aiForm.requirement || null
                }, {
                    timeout: 180000,
                    signal: abortController.signal
                });
                if (resp.data && Array.isArray(resp.data.questions)) {
                    aiGeneratedQuestions.value = resp.data.questions;
                    showMessage(`成功生成 ${resp.data.questions.length} 道题目`, 'success');
                }
            } catch (error) {
                if (error.name === 'CanceledError' || error.code === 'ERR_CANCELED') return;
                console.error('AI出题失败:', error);
                const msg = error.response?.data?.detail || error.message || '出题失败';
                showMessage(msg, 'error');
            } finally {
                isGenerating.value = false;
                abortController = null;
            }
        }

        function cancelGeneration() {
            if (abortController) {
                abortController.abort();
                isGenerating.value = false;
                showMessage('已终止生成', 'warning');
            }
        }

        function isGeneratedAdded(q) {
            return addedGeneratedKeys.has(q.question_no + '::' + q.question_text);
        }

        async function addGeneratedToBank(q) {
            if (isGeneratedAdded(q)) return;
            try {
                await axios.post('/api/question-bank', {
                    exam_id: null,
                    question_no: q.question_no,
                    question_text: q.question_text,
                    standard_answer: q.standard_answer,
                    analysis: q.analysis,
                    exam_filename: 'AI生成题目',
                    subject: aiForm.subject
                });
                addedGeneratedKeys.add(q.question_no + '::' + q.question_text);
                await fetchQuestionBank();
                showMessage('已加入题库', 'success');
            } catch (e) {
                const msg = e.response?.data?.detail || e.message;
                if (e.response?.status === 409) {
                    addedGeneratedKeys.add(q.question_no + '::' + q.question_text);
                    showMessage('该题目已在题库中', 'warning');
                } else {
                    showMessage('添加失败: ' + msg, 'error');
                }
            }
        }

        function openAnswerEditor() {
            if (!currentExam.value) return;
            editingQuestions.value = currentExam.value.questions.map(q => ({ ...q }));
            answerEditorVisible.value = true;
        }

        function addBlankQuestion() {
            editingQuestions.value.push({
                question_no: String(editingQuestions.value.length + 1),
                question_text: '', standard_answer: '', analysis: ''
            });
        }

        async function saveAnswers() {
            if (!selectedExamId.value) return;
            isSavingAnswers.value = true;
            try {
                await axios.put(`/api/exam/${selectedExamId.value}/answers`, {
                    questions: editingQuestions.value
                });
                showMessage('标准答案已保存', 'success');
                answerEditorVisible.value = false;
                await fetchExams();
            } catch (error) {
                console.error(error);
                showMessage(error.response?.data?.detail || '保存失败', 'error');
            } finally {
                isSavingAnswers.value = false;
            }
        }

        async function deleteExam() {
            if (!selectedExamId.value) return;
            try {
                await ElementPlus.ElMessageBox.confirm(
                    '确定要删除这份试题吗？删除后将无法恢复。',
                    '确认删除',
                    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
                );
            } catch {
                return;
            }
            isDeletingExam.value = true;
            try {
                await axios.delete(`/api/exam/${selectedExamId.value}`);
                showMessage('试题已删除', 'success');
                selectedExamId.value = '';
                await fetchExams();
            } catch (error) {
                console.error(error);
                showMessage(error.response?.data?.detail || '删除失败', 'error');
            } finally {
                isDeletingExam.value = false;
            }
        }

        async function deleteHistoryExam(examId) {
            try {
                await ElementPlus.ElMessageBox.confirm(
                    '确定要删除这份试题及其所有题目吗？',
                    '确认删除',
                    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
                );
            } catch {
                return;
            }
            try {
                await axios.delete(`/api/exam/${examId}`);
                showMessage('试题已删除', 'success');
                await fetchExams();
            } catch (error) {
                console.error(error);
                showMessage(error.response?.data?.detail || '删除失败', 'error');
            }
        }

        async function downloadRecord(correctionId) {
            try {
                const resp = await axios.get(`/api/correction/${correctionId}/record`, {
                    responseType: 'blob'
                });
                const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `correction_${correctionId}.docx`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (error) {
                console.error(error);
                showMessage('下载批改记录失败', 'error');
            }
        }

        function formatDate(s) {
            if (!s) return '';
            try { return new Date(s).toLocaleString('zh-CN'); } catch { return s; }
        }

        // ==================== 生命周期 ====================
        async function checkHealth() {
            try {
                const resp = await axios.get('/api/health', { timeout: 5000 });
                aiAvailable.value = resp.data?.ai_available !== false;
            } catch {
                aiAvailable.value = false;
            }
        }
        onMounted(() => {
            checkHealth();
            fetchHistory();
            fetchExams();
            fetchQuestionBank();
            fetchAllBankQuestions();

            document.addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    if (uploadFiles.value.length > 0 && !isLoading.value) {
                        e.preventDefault();
                        submitCorrection();
                    }
                }
            });
        });

        // ==================== 返回 ====================
        return {
            // 状态
            uploadFiles,
            previewUrls,
            correctionResult,
            renderedResult,
            isLoading,
            isStreaming,
            history,
            isDragOver,
            fileInput,

            // 试题相关状态
            exams,
            selectedExamId,
            currentExam,
            isExamUploading,
            examFileInput,
            answerEditorVisible,
            editingQuestions,
            isSavingAnswers,
            isDeletingExam,

            // 导航栏状态
            activeNav,
            questionDetailVisible,
            viewingQuestion,
            filteredQuestions,
            questionBank,
            filteredBank,

            // 搜索状态
            historyKeyword,
            bankQuestionNo,
            bankKeyword,

            // 分页状态
            examPage, examTotal, examPageSize,
            historyPage, historyTotal, historyPageSize,
            bankPage, bankTotal, bankPageSize,
            onExamPageChange(newPage) { examPage.value = newPage; fetchExams(); },
            onHistoryPageChange(newPage) { historyPage.value = newPage; fetchHistory(); },
            onBankPageChange(newPage) { bankPage.value = newPage; fetchQuestionBank(); },

            // 试卷生成状态
            examPaperSubject,
            examPaperCount,
            examPaperQuestions,
            examPaperAvailableCount,

            // AI 服务状态
            aiAvailable,

            // AI 出题状态
            aiGeneratedQuestions,
            aiForm,
            isGenerating,

            // 方法
            triggerFileInput,
            handleFileSelect,
            handleDragOver,
            handleDragLeave,
            handleDrop,
            removeFile,
            clearAllFiles,
            submitCorrection,
            submitCorrectionStream,
            fetchHistory,
            viewHistoryDetail,
            getScoreTagType,
            getSubjectTagType,

            // 导航栏方法
            viewQuestionDetail,
            clearBankSearch,
            highlightKeyword,
            isInBank,
            addToBank,
            removeFromBank,
            clearBank,
            fetchQuestionBank,
            fetchAllBankQuestions,
            allBankQuestions,

            // 试卷生成方法
            generateExamPaper,
            clearExamPaper,
            downloadExamPaper,

            // AI 出题方法
            generateQuestions,
            cancelGeneration,
            isGeneratedAdded,
            addGeneratedToBank,

            // 试题相关方法
            triggerExamFileInput,
            handleExamFileSelect,
            fetchExams,
            openAnswerEditor,
            addBlankQuestion,
            saveAnswers,
            deleteExam,
            deleteHistoryExam,
            downloadRecord,
            formatDate
        };
    }
});

// ==================== 注册 Element Plus Icons ====================
if (typeof ElementPlusIconsVue !== 'undefined') {
    for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
        app.component(key, component);
    }
}

// 使用 Element Plus
app.use(ElementPlus);

// 挂载应用
app.mount('#app');
