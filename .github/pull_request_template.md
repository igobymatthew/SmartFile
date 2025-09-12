# 📌 Pull Request: [Feature/Hotfix Title]

## ✨ Summary

- Describe the feature, bugfix, or refactor in plain language.
- Example: "Implements Rules Engine v1 with support for extension, regex, and mtime."

## ✅ Acceptance Criteria

- [ ] Config supports `type: extension|regex|mtime`, `pattern/when`, and `target_template`.
- [ ] Planner selects first matching rule; fallback if none.
- [ ] `dry-run` and `organize` use rules correctly.
- [ ] Destinations match `target_template`.

## 🧪 Test Results

- [ ] Unit tests added/updated and passing (`pytest`).
- [ ] Manual dry-run tested with sample files.
- [ ] CI workflow (Ruff + pytest) passing.

## 📚 Documentation

- [ ] Updated `README.md` with new usage.
- [ ] Updated `config.example.yml` with rule samples.
- [ ] Added/updated architecture or usage diagram if needed.

## 🔗 Related Issues

Closes #(issue-number)

---
⚡ **Checklist for Reviewer**

- Code follows style guide (Ruff, formatting).
- Clear variable/function names.
- Tests cover main paths and edge cases.
- Docs are clear and up-to-date.
