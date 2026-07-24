/* FaceAuth Enterprise — Main JavaScript
   ======================================= */

// == Constants ==
const API_BASE = '/api';

// == Toast Notification System ==
const Toast = {
  show(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = {
      success: 'fa-circle-check',
      error: 'fa-circle-xmark',
      warning: 'fa-triangle-exclamation',
      info: 'fa-circle-info',
    };

    const toast = document.createElement('div');
    toast.className = `toast custom-toast toast-${type} show`;
    toast.role = 'alert';
    toast.innerHTML = `
      <div class="toast-body d-flex align-items-center gap-2">
        <i class="fa-solid ${icons[type] || icons.info} fs-5"></i>
        <span class="flex-grow-1">${message}</span>
        <button type="button" class="btn-close btn-close-sm" data-bs-dismiss="toast"></button>
      </div>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      toast.remove();
    }, duration);
  },
  success(msg) { this.show(msg, 'success'); },
  error(msg) { this.show(msg, 'error', 6000); },
  warning(msg) { this.show(msg, 'warning'); },
  info(msg) { this.show(msg, 'info'); },
};

// == API Client ==
const API = {
  _getToken() {
    return localStorage.getItem('access_token');
  },

  _getHeaders(isFormData = false) {
    const headers = {};
    if (!isFormData) {
      headers['Content-Type'] = 'application/json';
    }
    const token = this._getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  },

  async request(method, path, data = null, isFormData = false) {
    const url = `${API_BASE}${path}`;
    const options = {
      method,
      headers: this._getHeaders(isFormData),
    };
    if (data) {
      options.body = isFormData ? data : JSON.stringify(data);
    }
    try {
      const response = await fetch(url, options);
      const contentType = response.headers.get('content-type');
      let result = null;
      if (contentType && contentType.includes('application/json')) {
        result = await response.json();
      } else {
        result = await response.text();
      }
      if (!response.ok) {
        const detail = result?.detail || result?.message || `HTTP ${response.status}`;
        const err = new Error(detail);
        err.status = response.status;
        err.data = result;
        throw err;
      }
      return result;
    } catch (err) {
      if (err.status) throw err;
      throw new Error('Network error. Please check your connection.');
    }
  },

  get(path) { return this.request('GET', path); },
  post(path, data, isFormData = false) { return this.request('POST', path, data, isFormData); },
  put(path, data) { return this.request('PUT', path, data); },
  patch(path, data) { return this.request('PATCH', path, data); },
  del(path) { return this.request('DELETE', path); },
};

// == Auth Helpers ==
const Auth = {
  isAuthenticated() {
    return !!localStorage.getItem('access_token');
  },

  getUser() {
    const data = localStorage.getItem('user_data');
    return data ? JSON.parse(data) : null;
  },

  setSession(token, refreshToken, userData = null) {
    localStorage.setItem('access_token', token);
    if (refreshToken) localStorage.setItem('refresh_token', refreshToken);
    if (userData) localStorage.setItem('user_data', JSON.stringify(userData));
  },

  clearSession() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_data');
  },

  async login(username, password) {
    const result = await API.post('/auth/login', { username, password });
    this.setSession(result.access_token, result.refresh_token);
    return result;
  },

  async register(data) {
    const result = await API.post('/auth/register', data);
    this.setSession(result.access_token, result.refresh_token);
    return result;
  },

  logout() {
    this.clearSession();
    window.location.href = '/login';
  },

  getAuthHeaders() {
    const token = localStorage.getItem('access_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  },

  async refreshToken() {
    const refresh = localStorage.getItem('refresh_token');
    if (!refresh) throw new Error('No refresh token');
    const result = await API.post('/auth/refresh', { refresh_token: refresh });
    localStorage.setItem('access_token', result.access_token);
    if (result.refresh_token) {
      localStorage.setItem('refresh_token', result.refresh_token);
    }
    return result;
  },
};

// == Form Validation ==
const Validator = {
  rules: {
    required: (v) => {
      if (v === null || v === undefined) return 'This field is required';
      if (typeof v === 'string' && v.trim() === '') return 'This field is required';
      if (typeof v === 'boolean' && !v) return 'This field is required';
      return null;
    },
    email: (v) => {
      if (!v || !v.trim()) return null; // Skip if empty (handled by required)
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()) ? null : 'Invalid email address';
    },
    minLength: (min) => (v) => (v && v.length >= min ? null : `Minimum ${min} characters`),
    maxLength: (max) => (v) => (v && v.length <= max ? null : `Maximum ${max} characters`),
    password: (v) => {
      if (!v) return 'Password must be at least 8 characters';
      const val = v; // Don't trim passwords (spaces might be intentional)
      if (val.length < 8) return 'Password must be at least 8 characters';
      if (!/[A-Z]/.test(val)) return 'Password must contain an uppercase letter';
      if (!/[a-z]/.test(val)) return 'Password must contain a lowercase letter';
      if (!/[0-9]/.test(val)) return 'Password must contain a number';
      return null;
    },
    match: (otherField, label) => (v) => {
      const otherEl = document.getElementById(otherField);
      const otherVal = otherEl ? otherEl.value : '';
      // Trim both for comparison
      const a = (v || '').trim();
      const b = (otherVal || '').trim();
      return a === b ? null : `Does not match ${label}`;
    },
    username: (v) => {
      if (!v) return 'Username must be at least 3 characters';
      const val = v.trim();
      if (val.length < 3) return 'Username must be at least 3 characters';
      if (!/^[a-zA-Z0-9_]+$/.test(val)) return 'Only letters, numbers, and underscores';
      return null;
    },
  },

  validateField(field) {
    const rawValue = field.value;
    const rulesAttr = field.dataset.validate;
    if (!rulesAttr) return true;

    // Determine if the field type should be trimmed
    const isPasswordField = field.type === 'password';
    const value = isPasswordField ? rawValue : rawValue.trim();

    const rulesList = rulesAttr.split('|');
    let firstError = null;

    for (const rule of rulesList) {
      let validator = this.rules[rule];
      let error = null;

      if (rule.startsWith('min:')) {
        const min = parseInt(rule.split(':')[1]);
        validator = this.rules.minLength(min);
      } else if (rule.startsWith('max:')) {
        const max = parseInt(rule.split(':')[1]);
        validator = this.rules.maxLength(max);
      } else if (rule.startsWith('match:')) {
        const params = rule.split(':');
        validator = this.rules.match(params[1], params[2] || 'other field');
      }

      if (validator) {
        error = validator(value);
      }

      if (error) {
        firstError = error;
        break;
      }
    }

    if (firstError) {
      field.classList.add('is-invalid');
      field.classList.remove('is-valid');
      const feedback = field.parentElement.querySelector('.invalid-feedback');
      if (feedback) feedback.textContent = firstError;
      else {
        const div = document.createElement('div');
        div.className = 'invalid-feedback';
        div.textContent = firstError;
        field.parentElement.appendChild(div);
      }
      return false;
    }

    // Field is valid
    field.classList.remove('is-invalid');
    field.classList.add('is-valid');
    const feedback = field.parentElement.querySelector('.invalid-feedback');
    if (feedback) feedback.textContent = '';
    return true;
  },

  validateForm(form) {
    let isValid = true;
    const fields = form.querySelectorAll('[data-validate]');
    fields.forEach((field) => {
      if (!this.validateField(field)) isValid = false;
    });
    return isValid;
  },

  // Re-validate a field and also any dependent match fields
  revalidateWithDependents(field) {
    this.validateField(field);
    // If this field is the source of a match, re-validate the match target
    const form = field.closest('form');
    if (form) {
      const matchFields = form.querySelectorAll('[data-validate*="match:"]');
      matchFields.forEach((mf) => {
        const rulesAttr = mf.dataset.validate || '';
        rulesAttr.split('|').forEach((rule) => {
          if (rule.startsWith('match:')) {
            const otherFieldId = rule.split(':')[1];
            if (otherFieldId === field.id) {
              this.validateField(mf);
            }
          }
        });
      });
    }
  },
};

// == Sidebar Toggle ==
function initSidebar() {
  const sidebar = document.querySelector('.sidebar');
  const toggle = document.querySelector('.sidebar-toggle');
  const overlay = document.querySelector('.sidebar-overlay');

  if (!sidebar) return;

  // Create toggle button if not exists
  if (!toggle) {
    const btn = document.createElement('button');
    btn.className = 'sidebar-toggle';
    btn.innerHTML = '<i class="fa-solid fa-bars"></i>';
    btn.setAttribute('aria-label', 'Toggle sidebar');
    document.body.prepend(btn);
    btn.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      let ov = document.querySelector('.sidebar-overlay');
      if (!ov) {
        ov = document.createElement('div');
        ov.className = 'sidebar-overlay';
        document.body.appendChild(ov);
        ov.addEventListener('click', () => {
          sidebar.classList.remove('open');
          ov.classList.remove('show');
        });
      }
      ov.classList.toggle('show');
    });
  }

  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('show');
    });
  }
}

// == Card Entrance Animation ==
function initCardAnimations() {
  const cards = document.querySelectorAll('.card:not(.no-animate)');
  cards.forEach((card, index) => {
    card.style.animationDelay = `${index * 80}ms`;
    card.classList.add('fade-in');
  });
}

// == Auto-dismiss alerts ==
function initAlerts() {
  document.querySelectorAll('.alert-dismissible').forEach((alert) => {
    setTimeout(() => {
      alert.classList.add('fade');
      setTimeout(() => alert.remove(), 300);
    }, 5000);
  });
}

// == Initialize on DOM ready ==
document.addEventListener('DOMContentLoaded', () => {
  initSidebar();
  initCardAnimations();
  initAlerts();

  // Real-time validation on blur and input
  document.querySelectorAll('[data-validate]').forEach((field) => {
    field.addEventListener('blur', () => Validator.validateField(field));
    field.addEventListener('input', () => {
      // Always re-validate on input once the field has been touched
      if (field.classList.contains('is-invalid') || field.classList.contains('is-valid')) {
        Validator.revalidateWithDependents(field);
      }
    });
  });

  // Form submit validation
  document.querySelectorAll('form[data-validate-form]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      if (!Validator.validateForm(form)) {
        e.preventDefault();
        Toast.error('Please fix the validation errors before submitting.');
      }
    });
  });
});

