(function() {
  'use strict';

  var isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  var sheet, backdrop, panel, searchInput, listEl;

  function init() {
    sheet = document.getElementById('picker-sheet');
    if (!sheet) return;
    backdrop = sheet.querySelector('.picker-backdrop');
    panel = sheet.querySelector('.picker-panel');
    searchInput = sheet.querySelector('.picker-search');
    listEl = sheet.querySelector('.picker-list');
  }

  var activeTrigger = null;
  var activeOptions = [];
  var activeRecent = [];

  function normalize(s) {
    return s.toLowerCase().replace(/[&.'\u2013\u2014-]+/g, '').trim();
  }

  function tokenize(s) {
    return normalize(s).split(/\s+/).filter(Boolean);
  }

  function score(optName, queryTokens) {
    var name = normalize(optName);
    if (queryTokens.length === 0) return 0;
    var queryStr = queryTokens.join(' ');
    if (name === queryStr) return 1000;
    if (name.startsWith(queryStr)) return 800;
    if (name.indexOf(queryStr) !== -1) return 600;

    var total = 300;
    for (var i = 0; i < queryTokens.length; i++) {
      var token = queryTokens[i];
      var pos = name.indexOf(token);
      if (pos === -1) {
        var si = 0, matched = false;
        for (var ci = 0; ci < token.length; ci++) {
          si = name.indexOf(token[ci], si);
          if (si === -1) break;
          si++;
          if (ci === token.length - 1) matched = true;
        }
        if (!matched) return 0;
        total += token.length + 1;
        continue;
      }
      total += 30 + token.length * 3;
      total -= pos * 0.3;

      var wordBoundary = pos === 0 || /[\s-]/.test(name[pos - 1]);
      if (wordBoundary) total += 40;
    }
    return total;
  }

  function filterOptions(query) {
    var tokens = tokenize(query);
    if (tokens.length === 0) {
      return { filtered: [], isRecent: true };
    }
    var scored = [];
    for (var i = 0; i < activeOptions.length; i++) {
      var s = score(activeOptions[i], tokens);
      if (s > 0) {
        scored.push({ name: activeOptions[i], score: s });
      }
    }
    scored.sort(function(a, b) { return b.score - a.score; });
    var seen = {};
    var result = [];
    for (var j = 0; j < scored.length; j++) {
      if (!seen[scored[j].name]) {
        seen[scored[j].name] = true;
        result.push(scored[j].name);
      }
    }
    return { filtered: result, isRecent: false };
  }

  function renderList(query) {
    var result = filterOptions(query);
    var items = result.filtered;

    if (items.length === 0 && !result.isRecent) {
      listEl.innerHTML = '<div class="picker-empty">No matches found</div>';
      return;
    }

    var html = '';
    if (result.isRecent && activeRecent.length > 0) {
      html += '<div class="picker-group-label">Recent</div>';
      for (var r = 0; r < activeRecent.length && r < 5; r++) {
        html += '<button type="button" class="picker-option" data-value="' + attrEsc(activeRecent[r]) + '">' + escHtml(activeRecent[r]) + '</button>';
      }
      var remaining = [];
      for (var o = 0; o < activeOptions.length; o++) {
        if (activeRecent.indexOf(activeOptions[o]) === -1) {
          remaining.push(activeOptions[o]);
        }
      }
      if (remaining.length > 0) {
        html += '<div class="picker-group-label">All exercises</div>';
        for (var k = 0; k < remaining.length; k++) {
          html += '<button type="button" class="picker-option" data-value="' + attrEsc(remaining[k]) + '">' + escHtml(remaining[k]) + '</button>';
        }
      }
    } else {
      for (var i = 0; i < items.length; i++) {
        html += '<button type="button" class="picker-option" data-value="' + attrEsc(items[i]) + '">' + escHtml(items[i]) + '</button>';
      }
    }
    listEl.innerHTML = html;
  }

  function attrEsc(s) {
    return s.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function escHtml(s) {
    return s.replace(/[<>&]/g, function(c) {
      return c === '<' ? '&lt;' : c === '>' ? '&gt;' : '&amp;';
    });
  }

  function openPicker(trigger) {
    if (activeTrigger === trigger && sheet.classList.contains('open')) {
      closePicker();
      return;
    }
    activeTrigger = trigger;
    try {
      activeOptions = JSON.parse(trigger.getAttribute('data-options') || '[]');
      activeRecent = JSON.parse(trigger.getAttribute('data-recent') || '[]');
    } catch(e) {
      activeOptions = [];
      activeRecent = [];
    }
    searchInput.value = '';
    renderList('');
    sheet.classList.add('open');

    var currentVal = trigger.textContent.trim();
    if (currentVal && currentVal !== trigger.getAttribute('data-placeholder')) {
      var selected = listEl.querySelector('[data-value="' + attrEsc(currentVal) + '"]');
      if (selected) selected.classList.add('selected');
    }

    if (!isTouch) {
      setTimeout(function() { searchInput.focus(); }, 200);
    }
  }

  function closePicker() {
    sheet.classList.remove('open');
    if (activeTrigger) {
      activeTrigger.focus();
    }
    activeTrigger = null;
    activeOptions = [];
    activeRecent = [];
    searchInput.value = '';
    listEl.innerHTML = '';
  }

  function selectOption(value) {
    if (!activeTrigger) return;
    var targetId = activeTrigger.getAttribute('data-target');
    var hidden = document.getElementById(targetId);
    if (!hidden) return;
    hidden.value = value;
    activeTrigger.textContent = value;
    activeTrigger.classList.remove('picker-error');
    var evtChange = document.createEvent('Event');
    evtChange.initEvent('change', true, true);
    hidden.dispatchEvent(evtChange);
    var evtInput = document.createEvent('Event');
    evtInput.initEvent('input', true, true);
    hidden.dispatchEvent(evtInput);
    closePicker();
  }

  function initSheetHandlers() {
    if (!sheet) return;

    sheet.addEventListener('click', function(e) {
      var opt = e.target.closest('.picker-option');
      if (opt && opt.dataset.value) {
        e.preventDefault();
        selectOption(opt.dataset.value);
        return;
      }
      if (e.target.closest('.picker-backdrop')) {
        closePicker();
      }
      if (e.target.closest('.picker-close')) {
        closePicker();
      }
    });

    searchInput.addEventListener('input', function() {
      renderList(this.value);
    });

    searchInput.addEventListener('keydown', function(e) {
      var items = listEl.querySelectorAll('.picker-option');
      if (items.length === 0) return;
      var current = listEl.querySelector('.picker-option.highlighted');
      var idx = -1;
      if (current) { idx = Array.prototype.indexOf.call(items, current); }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (current) current.classList.remove('highlighted');
        idx = Math.min(idx + 1, items.length - 1);
        items[idx].classList.add('highlighted');
        items[idx].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (current) current.classList.remove('highlighted');
        idx = Math.max(idx - 1, 0);
        items[idx].classList.add('highlighted');
        items[idx].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (current && current.dataset.value) {
          selectOption(current.dataset.value);
        }
      } else if (e.key === 'Escape') {
        closePicker();
      }
    });

    listEl.addEventListener('mouseover', function(e) {
      var opt = e.target.closest('.picker-option');
      if (!opt) return;
      var highlighted = listEl.querySelector('.picker-option.highlighted');
      if (highlighted) highlighted.classList.remove('highlighted');
      opt.classList.add('highlighted');
    });
  }

  document.addEventListener('DOMContentLoaded', function() {
    init();
    initSheetHandlers();
  });

  document.addEventListener('click', function(e) {
    var trigger = e.target.closest('[data-picker-trigger]');
    if (trigger) {
      e.preventDefault();
      openPicker(trigger);
    }
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && sheet && sheet.classList.contains('open')) {
      closePicker();
    }
  });

  document.addEventListener('htmx:beforeRequest', function(e) {
    var form = e.target.closest('.one-rm-form, .benchmark-form');
    if (!form) return;
    var trigger = form.querySelector('[data-picker-trigger]');
    if (!trigger) return;
    var targetId = trigger.getAttribute('data-target');
    var hidden = document.getElementById(targetId);
    if (!hidden || !hidden.value.trim()) {
      e.preventDefault();
      trigger.classList.add('picker-error');
      trigger.textContent = 'Please select an option';
    }
  });

  document.addEventListener('htmx:afterSettle', function(e) {
    var swapContent = e.detail.elt;
    var trigger = swapContent.querySelector('[data-picker-trigger]');
    if (!trigger) return;
    var targetId = trigger.getAttribute('data-target');
    var hidden = document.getElementById(targetId);
    if (hidden && hidden.value) {
      trigger.textContent = hidden.value;
    } else {
      trigger.textContent = trigger.getAttribute('data-placeholder') || 'Select…';
    }
  });
})();