# Theme System Testing Guide

## Overview

Comprehensive testing strategy for DependIQ's theme system, covering unit tests, integration tests, CSS validation, and end-to-end testing.

## Test Coverage

### Current Test Stats
- **Total Tests**: 231 (229 passed, 2 skipped)
- **Theme-Specific Tests**: 24 tests
- **Coverage Areas**:
  - ✅ Theme validation (API)
  - ✅ Theme persistence (Database)
  - ✅ Theme model operations
  - ✅ CSS definitions and structure
  - ✅ Color value validation
  - ✅ Theme switching workflows

## Test Files

### [`tests/test_themes.py`](../tests/test_themes.py)
**Purpose**: Unit and integration tests for theme functionality

**Test Classes**:
- `TestThemeValidation` - Validates API accepts/rejects themes correctly
- `TestThemeModel` - Tests UserPreference model theme fields
- `TestThemePersistence` - Verifies themes persist across requests
- `TestThemeWithOtherPreferences` - Tests theme updates with other preferences
- `TestNewThemes` - Specific tests for Phase 1 themes (ocean, forest, nord, dracula, system)

**Run**:
```bash
pytest tests/test_themes.py -v
```

### [`tests/test_theme_css.py`](../tests/test_theme_css.py)
**Purpose**: CSS validation and structure tests

**Test Classes**:
- `TestThemeCSSDefinitions` - Verifies all themes have CSS definitions
- `TestThemeCSSStructure` - Validates CSS organization
- `TestCSSColorValues` - Tests color values are valid hex
- `TestCSSComments` - Ensures proper documentation

**Run**:
```bash
pytest tests/test_theme_css.py -v
```

## Running Tests

### All Tests
```bash
make test
```

### Theme Tests Only
```bash
pytest tests/test_themes.py tests/test_theme_css.py -v
```

### With Coverage
```bash
pytest tests/test_themes.py --cov=app.api.user --cov=app.models.user_preference --cov-report=html
```

### Watch Mode (Auto-rerun on changes)
```bash
pytest-watch tests/test_themes.py
```

## Test Scenarios Covered

### ✅ Theme Validation
- [x] All 7 valid themes accepted (light, dark, ocean, forest, nord, dracula, system)
- [x] Invalid themes rejected with 400 error
- [x] Case-sensitive validation
- [x] Error messages are descriptive

### ✅ Theme Model
- [x] Default theme is "light"
- [x] Theme field accommodates all theme names (30 chars)
- [x] theme_auto_mode field is nullable
- [x] to_dict() includes theme

### ✅ Theme Persistence
- [x] Theme persists after update
- [x] Theme included in profile response
- [x] Multiple rapid updates handled correctly
- [x] Theme preserved when updating other preferences

### ✅ CSS Validation
- [x] All themes have CSS definitions
- [x] All required CSS variables defined
- [x] Color values are valid hex codes
- [x] Dark themes have supporting styles
- [x] File size is reasonable
- [x] Descriptive comments present

### ✅ Integration
- [x] Theme updates work with authentication
- [x] Theme persists across API calls
- [x] Theme works with other preferences
- [x] Unauthorized access properly rejected

## Issues These Tests Catch

1. **Missing CSS Definitions** ❌
   - `test_all_themes_have_css_definitions` catches missing theme CSS

2. **Invalid Theme Names** ❌
   - `test_invalid_theme_rejected` catches typos in theme names

3. **Missing CSS Variables** ❌
   - `test_theme_has_required_css_variables` catches incomplete theme definitions

4. **Database Schema Issues** ❌
   - `test_theme_field_length` would catch if field is too small

5. **Persistence Failures** ❌
   - `test_theme_persists_after_update` catches if theme doesn't save

6. **Invalid Colors** ❌
   - `test_color_values_are_valid_hex` catches malformed color codes

7. **API Validation Bugs** ❌
   - `test_all_valid_themes_accepted` catches if valid theme is rejected

## Adding New Tests

### For New Themes

When adding a new theme, add tests in [`test_themes.py`](../tests/test_themes.py):

```python
def test_new_theme_name(self, test_client, auth_headers):
    """New theme should work"""
    response = test_client.put(
        "/api/user/preferences",
        headers=auth_headers,
        json={"theme": "new_theme"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["theme"] == "new_theme"
```

### For CSS Changes

Add to [`test_theme_css.py`](../tests/test_theme_css.py):

```python
def test_new_theme_has_required_styles(self):
    """New theme should have all required styles"""
    with open('static/css/main.css', 'r') as f:
        css = f.read()

    assert 'body[data-theme="new_theme"]' in css
```

## CI/CD Integration

### Pre-commit Hook

Tests run automatically before commits:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: theme-tests
        name: Theme Tests
        entry: pytest tests/test_themes.py tests/test_theme_css.py -x
        language: system
        pass_filenames: false
```

### GitHub Actions

Automated testing on push/PR:

```yaml
# .github/workflows/tests.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: make test
```

## Test Maintenance

### When to Update Tests

1. **Adding new theme**: Add test in `TestNewThemes` class
2. **Changing validation**: Update `TestThemeValidation`
3. **Modifying CSS**: Update `TestThemeCSSDefinitions`
4. **Adding CSS variables**: Update `test_theme_has_required_css_variables`

### Monthly Review

- Check test execution time (should be < 1 minute for theme tests)
- Review coverage report
- Update tests for any deprecations
- Add tests for reported bugs

## Debugging Test Failures

### Theme Not Accepted
```python
# Check valid_themes list in app/api/user.py
# Should match themes in test
```

### CSS Not Found
```python
# Verify theme CSS block exists in static/css/main.css
# Check regex pattern in test matches actual CSS
```

### Persistence Fails
```python
# Check database migration ran: alembic current
# Verify theme field is 30 chars: \d user_preferences
```

## Performance Benchmarks

Expected test execution times:
- `test_themes.py`: ~2-3 seconds
- `test_theme_css.py`: <1 second
- Full test suite: ~30-40 seconds

## Future Test Additions

### Phase 2 (Accessibility)
- High contrast mode tests
- Colorblind mode validation
- WCAG compliance automated checks
- Font size preference tests

### Phase 3 (E2E)
- Playwright browser tests
- Visual regression tests
- Theme switching UI tests
- Cross-browser compatibility

---

**Last Updated**: 2025-11-30
**Test Framework**: pytest 8.4.2
**Total Theme Tests**: 24
