/**
 * Website SaaS Landing Page - External JavaScript
 * This file can be used for additional functionality or enhancements
 * Main scripts are embedded in the template for better performance
 */

(function() {
  'use strict';

  function initAuthPages() {
    var authRoot = document.querySelector('.oe_website_login_container');
    if (!authRoot || authRoot.dataset.moAuthReady === 'true') {
      return;
    }
    authRoot.dataset.moAuthReady = 'true';

    var iconMap = [
      ['input[name="login"], input[type="email"]', 'email'],
      ['input[name="password"], input[type="password"]', 'password'],
      ['input[name="confirm_password"]', 'confirm_password'],
      ['input[name="name"]', 'name'],
      ['input[name="company_name"]', 'company'],
      ['input[name="phone"]', 'phone']
    ];

    iconMap.forEach(function(rule) {
      authRoot.querySelectorAll(rule[0]).forEach(function(input) {
        var field = input.closest('.mb-3, .form-group, .field-password, .field-login, .input-group') || input.parentElement;
        if (field && !field.classList.contains('mo-auth-field')) {
          field.classList.add('mo-auth-field');
          field.dataset.authIcon = rule[1];
        }
      });
    });

    authRoot.querySelectorAll('input[type="password"]').forEach(function(input) {
      var group = input.closest('.input-group');
      if (group && group.querySelector('.o_show_password, .mo-auth-password-toggle')) {
        return;
      }

      if (!group) {
        group = document.createElement('div');
        group.className = 'input-group';
        input.parentNode.insertBefore(group, input);
        group.appendChild(input);
      }

      var toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'btn mo-auth-password-toggle';
      toggle.setAttribute('aria-label', 'Show password');
      toggle.textContent = 'Show';
      group.appendChild(toggle);

      toggle.addEventListener('click', function() {
        var isHidden = input.type === 'password';
        input.type = isHidden ? 'text' : 'password';
        toggle.textContent = isHidden ? 'Hide' : 'Show';
        toggle.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
      });
    });

    var primaryPassword = authRoot.querySelector('.oe_signup_form input[name="password"], .oe_reset_password_form input[name="password"], .oe_reset_password_form input[name="new_password"]');
    if (primaryPassword) {
      var strength = document.createElement('div');
      strength.className = 'mo-auth-strength';
      strength.dataset.score = '0';
      strength.innerHTML = '<div class="mo-auth-strength-track"><span></span><span></span><span></span><span></span></div><div class="mo-auth-strength-text">Use at least 8 characters with a mix of letters, numbers, and symbols.</div>';

      var host = primaryPassword.closest('.mb-3, .form-group, .input-group') || primaryPassword.parentElement;
      host.insertAdjacentElement('afterend', strength);

      primaryPassword.addEventListener('input', function() {
        var value = primaryPassword.value || '';
        var score = 0;
        if (value.length >= 8) score += 1;
        if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1;
        if (/\d/.test(value)) score += 1;
        if (/[^A-Za-z0-9]/.test(value)) score += 1;

        strength.classList.toggle('is-visible', value.length > 0);
        strength.dataset.score = String(score);

        var labels = ['Very weak', 'Weak', 'Fair', 'Strong', 'Excellent'];
        strength.querySelector('.mo-auth-strength-text').textContent = labels[score] || labels[0];
      });
    }

    authRoot.querySelectorAll('form').forEach(function(form) {
      form.addEventListener('submit', function() {
        var button = form.querySelector('button[type="submit"], input[type="submit"], .btn-primary');
        if (!button) {
          return;
        }
        button.classList.add('mo-auth-loading');
        if (button.tagName === 'INPUT') {
          button.dataset.originalValue = button.value;
          button.value = 'Please wait...';
        } else {
          button.dataset.originalText = button.textContent;
          button.textContent = 'Please wait...';
        }
      });
    });
  }

  /**
   * Initialize landing page enhancements
   */
  function initLandingPage() {
    // Add any additional functionality here
    initAuthPages();
  }

  /**
   * Handle window load event
   */
  window.addEventListener('load', function() {
    initLandingPage();
  });

  /**
   * Handle DOM ready
   */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLandingPage);
  } else {
    initLandingPage();
  }

})();
