/**
 * V3.2 Amazon Product Research - Main application logic.
 */
(function () {
    'use strict';

    // State
    let currentProjectId = null;
    let currentJobId = null;
    let pollTimer = null;
    let workflowDef = null;
    const keywords = [];
    const categories = [];

    // DOM helpers
    const $ = (id) => document.getElementById(id);
    const show = (el) => el.classList.remove('hidden');
    const hide = (el) => el.classList.add('hidden');

    function alertInfo(msg) { showAlert(msg, 'info'); }
    function alertWarn(msg) { showAlert(msg, 'warning'); }
    function alertErr(msg) { showAlert(msg, 'error'); }
    function showAlert(msg, type) {
        const div = $('global-alert');
        div.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
        setTimeout(() => { div.innerHTML = ''; }, 5000);
    }

    // ---- Tag input ----
    function setupTagInput(inputId, listId, arr) {
        const input = $(inputId);
        const list = $(listId);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && input.value.trim()) {
                const val = input.value.trim();
                if (!arr.includes(val)) {
                    arr.push(val);
                    renderTags(list, arr);
                }
                input.value = '';
            }
        });
    }
    function renderTags(list, arr) {
        list.innerHTML = arr.map((t, i) =>
            `<span class="tag">${t}<button data-i="${i}">×</button></span>`
        ).join('');
        list.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', () => {
                arr.splice(parseInt(btn.dataset.i), 1);
                renderTags(list, arr);
            });
        });
    }

    // ---- Login ----
    $('btn-login').addEventListener('click', async () => {
        const token = $('invite-token').value.trim();
        if (!token) { alertErr('请输入邀请码'); return; }
        try {
            const data = await Api.login(token);
            $('user-id').textContent = `用户: ${data.user_id.slice(0, 8)}`;
            showWorkbench();
        } catch (e) {
            $('login-error').textContent = e.message;
            show($('login-error'));
        }
    });
    $('invite-token').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') $('btn-login').click();
    });

    $('btn-logout').addEventListener('click', async () => {
        await Api.logout().catch(() => {});
        location.reload();
    });

    async function showWorkbench() {
        hide($('login-view'));
        show($('workbench-view'));
        setupTagInput('keyword-input', 'keyword-tags', keywords);
        setupTagInput('category-input', 'category-tags', categories);
        // Load workflow definition for dynamic agent rendering
        try {
            workflowDef = await Api.workflowDefinition();
            renderAgentPipeline([]);
        } catch (e) { /* fallback */ }
    }

    // ---- Agent pipeline (dynamic from API) ----
    function renderAgentPipeline(completedAgents) {
        const container = $('agent-pipeline');
        if (!workflowDef) { container.innerHTML = ''; return; }
        let html = '';
        for (const phase of workflowDef.phases) {
            for (const agent of phase.agents) {
                const cls = completedAgents.includes(agent) ? 'done' : '';
                html += `<div class="agent-step ${cls}" title="${phase.name}">${agent}</div>`;
            }
        }
        container.innerHTML = html;
    }

    // ---- Project ----
    $('btn-create-project').addEventListener('click', async () => {
        const name = $('project-name').value.trim();
        if (!name) { alertErr('请输入项目名称'); return; }
        try {
            const data = {
                project_name: name,
                marketplace: $('marketplace').value,
                keywords: [...keywords],
                categories: [...categories],
                target_price_range: {
                    min: $('price-min').value || null,
                    max: $('price-max').value || null,
                    currency: $('price-currency').value || 'USD',
                },
                urls: $('url-list').value.split('\n').map(s => s.trim()).filter(Boolean),
            };
            const proj = await Api.createProject(data);
            currentProjectId = proj.project_id;
            $('project-status').innerHTML = `<span class="badge badge-confirmed">已创建: ${proj.project_id.slice(0,8)}</span>`;
            alertInfo('项目已创建');
        } catch (e) { alertErr(e.message); }
    });

    // ---- File upload ----
    $('btn-upload').addEventListener('click', async () => {
        if (!currentProjectId) { alertErr('请先创建项目'); return; }
        const files = $('file-input').files;
        if (!files.length) { alertWarn('请选择文件'); return; }
        const fd = new FormData();
        for (const f of files) fd.append('file', f);
        try {
            const result = await Api.uploadFiles(currentProjectId, fd);
            let html = '';
            for (const u of result.uploads || []) {
                html += `<div class="badge badge-confirmed" style="margin-right:6px;">${u.original_name} (${u.size_bytes}B)</div>`;
            }
            for (const e of result.errors || []) {
                html += `<div class="alert alert-error" style="margin-top:4px;">${e}</div>`;
            }
            $('upload-results').innerHTML = html;
            alertInfo(`上传完成: ${(result.uploads||[]).length} 个文件`);
        } catch (e) { alertErr(e.message); }
    });

    $('btn-detect').addEventListener('click', async () => {
        if (!currentProjectId) { alertErr('请先创建项目'); return; }
        try {
            const result = await Api.detectFiles(currentProjectId);
            let html = '<table><thead><tr><th>文件</th><th>类型</th><th>置信度</th><th>识别列</th></tr></thead><tbody>';
            for (const f of result.files || []) {
                html += `<tr><td>${f.original_name}</td><td>${f.detected_type}</td><td>${f.confidence}</td><td>${(f.recognized_columns||[]).join(', ')}</td></tr>`;
            }
            html += '</tbody></table>';
            $('upload-results').innerHTML = html;
        } catch (e) { alertErr(e.message); }
    });

    // ---- Template upload ----
    $('btn-upload-template').addEventListener('click', async () => {
        if (!currentProjectId) { alertErr('请先创建项目'); return; }
        const file = $('template-input').files[0];
        if (!file) { alertWarn('请选择模板文件'); return; }
        const fd = new FormData();
        fd.append('file', file);
        fd.append('template_type', $('template-type').value);
        try {
            const t = await Api.uploadTemplate(currentProjectId, fd);
            $('template-list').innerHTML = `<div class="badge badge-confirmed">${t.original_name} - ${t.template_type} (${t.validation_status})</div>`;
        } catch (e) { alertErr(e.message); }
    });

    // ---- Validate ----
    $('btn-validate').addEventListener('click', async () => {
        if (!currentProjectId) { alertErr('请先创建项目'); return; }
        try {
            const r = await Api.validateProject(currentProjectId);
            let msg = r.valid ? '校验通过' : '校验未通过';
            if (r.warnings?.length) msg += '<br>警告: ' + r.warnings.join('; ');
            if (r.pending_manual_inputs?.length) msg += '<br>待补充: ' + r.pending_manual_inputs.join('; ');
            r.valid ? alertInfo(msg) : alertWarn(msg);
        } catch (e) { alertErr(e.message); }
    });

    // ---- Start analysis ----
    $('btn-start-analysis').addEventListener('click', async () => {
        if (!currentProjectId) { alertErr('请先创建项目'); return; }
        try {
            const job = await Api.createJob(currentProjectId, {
                allow_url_fetch: $('url-fetch-enabled').checked,
                use_mock_data: false,
            });
            currentJobId = job.job_id;
            $('job-status').innerHTML = `<span class="badge badge-queued">${job.status}</span>`;
            show($('btn-cancel-job'));
            startPolling();
        } catch (e) { alertErr(e.message); }
    });

    $('btn-cancel-job').addEventListener('click', async () => {
        if (!currentJobId) return;
        if (!confirm('确定取消当前任务？')) return;
        try {
            await Api.cancelJob(currentJobId);
            alertInfo('取消请求已发送');
        } catch (e) { alertErr(e.message); }
    });

    function startPolling() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(pollJob, 2000);
    }

    async function pollJob() {
        if (!currentJobId) return;
        try {
            const job = await Api.getJob(currentJobId);
            $('job-status').innerHTML = `<span class="badge badge-${job.status}">${job.status}</span>`;
            $('progress-info').textContent = `Agent: ${job.current_agent || '-'} | 进度: ${job.progress}%`;
            renderAgentPipeline(job.completed_agents || []);

            if (['completed', 'failed', 'cancelled'].includes(job.status)) {
                clearInterval(pollTimer);
                pollTimer = null;
                hide($('btn-cancel-job'));
                if (job.status === 'completed') {
                    alertInfo('分析完成');
                    loadCandidates();
                    loadOutputs();
                } else if (job.status === 'failed') {
                    alertErr('分析失败: ' + (job.errors?.[0] || ''));
                }
            }
        } catch (e) { /* network errors during polling */ }
    }

    // ---- Candidates ----
    async function loadCandidates() {
        if (!currentProjectId) return;
        try {
            const cands = await Api.listCandidates(currentProjectId);
            const tbody = $('candidates-table').querySelector('tbody');
            tbody.innerHTML = cands.map(c => {
                const data = typeof c.candidate_data === 'string' ? {} : (c.candidate_data || {});
                const name = data.product_name || data.name || c.candidate_id.slice(0, 8);
                return `<tr>
                    <td>${name}</td>
                    <td><span class="badge badge-${c.status}">${c.status}</span></td>
                    <td>
                        <button class="btn btn-success btn-sm" onclick="confirmCand('${c.candidate_id}')">确认</button>
                        <button class="btn btn-danger btn-sm" onclick="rejectCand('${c.candidate_id}')">拒绝</button>
                    </td>
                </tr>`;
            }).join('') || '<tr><td colspan="3">暂无候选</td></tr>';
        } catch (e) { /* ignore */ }
    }
    window.confirmCand = async (cid) => {
        try { await Api.confirmCandidate(currentProjectId, cid); loadCandidates(); }
        catch (e) { alertErr(e.message); }
    };
    window.rejectCand = async (cid) => {
        try { await Api.rejectCandidate(currentProjectId, cid); loadCandidates(); }
        catch (e) { alertErr(e.message); }
    };

    // ---- Continue development ----
    $('btn-continue-dev').addEventListener('click', async () => {
        if (!currentProjectId) { alertErr('请先创建项目'); return; }
        try {
            const r = await Api.continueDevelopment(currentProjectId);
            if (r.status === 'waiting_for_confirmation') {
                alertWarn(r.message);
            } else {
                currentJobId = r.job_id;
                $('job-status').innerHTML = `<span class="badge badge-queued">Phase 2: ${r.status}</span>`;
                show($('btn-cancel-job'));
                startPolling();
                alertInfo('Phase 2 已启动');
            }
        } catch (e) { alertErr(e.message); }
    });

    // ---- Manual inputs ----
    $('btn-save-manual').addEventListener('click', async () => {
        if (!currentProjectId) { alertErr('请先创建项目'); return; }
        const data = {
            supplier_name: $('mi-supplier').value,
            purchase_cost: $('mi-cost').value,
            moq: $('mi-moq').value,
            logistics: $('mi-logistics').value,
            shipping_cost: $('mi-shipping').value,
            target_margin: $('mi-margin').value,
        };
        try {
            await Api.saveManualInputs(currentProjectId, data);
            alertInfo('人工信息已保存（空值保留为空）');
        } catch (e) { alertErr(e.message); }
    });

    // ---- Outputs ----
    async function loadOutputs() {
        if (!currentProjectId) return;
        try {
            const outs = await Api.listOutputs(currentProjectId);
            const tbody = $('outputs-table').querySelector('tbody');
            tbody.innerHTML = outs.map(o =>
                `<tr>
                    <td>${o.output_type}</td>
                    <td>${o.file_name}</td>
                    <td>${o.size_bytes} B</td>
                    <td><a href="${Api.downloadUrl(o.output_id)}" class="btn btn-primary btn-sm">下载</a></td>
                </tr>`
            ).join('') || '<tr><td colspan="4">暂无输出文件</td></tr>';
        } catch (e) { /* ignore */ }
    }

    // Check session on load
    Api.me().then(d => {
        $('user-id').textContent = `用户: ${d.user_id.slice(0, 8)}`;
        showWorkbench();
    }).catch(() => { /* stay on login */ });
})();
