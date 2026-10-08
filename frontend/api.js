/**
 * API client for the Amazon Product Research backend.
 * All requests go through this module so auth/CSRF handling is centralized.
 */
(function (global) {
    'use strict';

    const API_BASE = '';

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    function setCsrfToken(token) {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) meta.content = token;
    }

    async function request(method, path, body) {
        const headers = {};
        if (body !== undefined) {
            headers['Content-Type'] = 'application/json';
        }
        const csrf = getCsrfToken();
        if (csrf && method !== 'GET') {
            headers['X-CSRF-Token'] = csrf;
        }
        const opts = { method, headers, credentials: 'same-origin' };
        if (body !== undefined) {
            opts.body = JSON.stringify(body);
        }
        const resp = await fetch(API_BASE + path, opts);
        const text = await resp.text();
        let data;
        try { data = text ? JSON.parse(text) : null; } catch { data = text; }
        if (!resp.ok) {
            const err = new Error(data?.error || `HTTP ${resp.status}`);
            err.status = resp.status;
            err.data = data;
            throw err;
        }
        return data;
    }

    async function uploadMultipart(path, formData) {
        const csrf = getCsrfToken();
        const headers = {};
        if (csrf) headers['X-CSRF-Token'] = csrf;
        const resp = await fetch(API_BASE + path, {
            method: 'POST',
            headers,
            body: formData,
            credentials: 'same-origin',
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
        return data;
    }

    const api = {
        // Auth
        login: (token) => request('POST', '/api/auth/login', { token }).then(d => {
            setCsrfToken(d.csrf_token);
            return d;
        }),
        logout: () => request('POST', '/api/auth/logout'),
        me: () => request('GET', '/api/auth/me'),

        // Health & workflow
        health: () => request('GET', '/api/health'),
        workflowDefinition: () => request('GET', '/api/workflow/definition'),

        // Projects
        createProject: (data) => request('POST', '/api/projects', data),
        getProject: (id) => request('GET', `/api/projects/${id}`),
        updateProject: (id, data) => request('PUT', `/api/projects/${id}`, data),
        listProjects: () => request('GET', '/api/projects'),
        validateProject: (id) => request('POST', `/api/projects/${id}/validate`),

        // Files
        uploadFiles: (projectId, formData) => uploadMultipart(`/api/projects/${projectId}/files`, formData),
        listFiles: (projectId) => request('GET', `/api/projects/${projectId}/files`),
        detectFiles: (projectId) => request('POST', `/api/projects/${projectId}/files/detect`),

        // Templates
        uploadTemplate: (projectId, formData) => uploadMultipart(`/api/projects/${projectId}/templates`, formData),
        listTemplates: (projectId) => request('GET', `/api/projects/${projectId}/templates`),

        // Jobs
        createJob: (projectId, data) => request('POST', `/api/projects/${projectId}/jobs`, data),
        getJob: (jobId) => request('GET', `/api/jobs/${jobId}`),
        cancelJob: (jobId) => request('POST', `/api/jobs/${jobId}/cancel`),

        // Candidates
        listCandidates: (projectId) => request('GET', `/api/projects/${projectId}/candidates`),
        confirmCandidate: (projectId, cid) => request('POST', `/api/projects/${projectId}/candidates/${cid}/confirm`),
        rejectCandidate: (projectId, cid) => request('POST', `/api/projects/${projectId}/candidates/${cid}/reject`),

        // Manual inputs & continue
        saveManualInputs: (projectId, data) => request('PUT', `/api/projects/${projectId}/manual-inputs`, data),
        continueDevelopment: (projectId) => request('POST', `/api/projects/${projectId}/continue-development`),

        // Outputs
        listOutputs: (projectId) => request('GET', `/api/projects/${projectId}/outputs`),
        downloadUrl: (outputId) => `${API_BASE}/api/outputs/${outputId}/download`,
    };

    global.Api = api;
})(window);
