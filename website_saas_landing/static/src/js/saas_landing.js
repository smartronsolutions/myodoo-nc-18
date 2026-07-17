/**
 * Website SaaS Landing Page - External JavaScript
 * This file can be used for additional functionality or enhancements
 * Main scripts are embedded in the template for better performance
 */

(function() {
  'use strict';

  /**
   * Initialize landing page enhancements
   */
  function initLandingPage() {
    document.documentElement.classList.add('mo_saas_ready');
  }

  function closeAccountDropdown() {
    var account = document.getElementById('mo_account');
    if (!account) return;
    var button = account.querySelector('#mo_account_btn');
    var dropdown = account.querySelector('#mo_account_drop');
    if (button) {
      button.classList.remove('mo_active_btn');
      button.setAttribute('aria-expanded', 'false');
    }
    if (dropdown) dropdown.classList.remove('mo_open');
  }

  /* Delegation survives Odoo frontend navigation and dynamic layout updates. */
  document.addEventListener('click', function (event) {
    var accountButton = event.target.closest('#mo_account_btn');
    if (accountButton) {
      event.preventDefault();
      event.stopPropagation();
      var account = accountButton.closest('#mo_account');
      var dropdown = account && account.querySelector('#mo_account_drop');
      if (!dropdown) return;
      var opening = !dropdown.classList.contains('mo_open');
      closeAccountDropdown();
      if (opening) {
        dropdown.classList.add('mo_open');
        accountButton.classList.add('mo_active_btn');
        accountButton.setAttribute('aria-expanded', 'true');
      }
      return;
    }

    if (!event.target.closest('#mo_account')) closeAccountDropdown();
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closeAccountDropdown();
  });

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
