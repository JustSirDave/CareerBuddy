# CareerBuddy Testing Strategy & Documentation

**Created**: January 13, 2026  
**Test Framework**: pytest  
**Coverage Goal**: 80%+ for critical paths

---

## 📊 **Test Coverage Overview**

### **Test Suite Statistics**

| Category | Test Files | Test Count | Coverage |
|----------|------------|------------|----------|
| **Models** | 1 | 50+ tests | Database operations, relationships, validation |
| **Services** | 4 | 120+ tests | Business logic, conversation flows, rendering |
| **API** | 1 | 30+ tests | Webhooks, endpoints, security |
| **Integration** | 1 | 25+ tests | End-to-end workflows, system integration |
| **TOTAL** | **7 files** | **225+ tests** | **Comprehensive** |

### **Critical Path Coverage**

✅ **Resume Creation Flow** - Complete  
✅ **CV Creation Flow** - Complete  
✅ **Cover Letter Flow** - Complete  
✅ **Payment Processing** - Complete  
✅ **Document Rendering** - All 3 templates  
✅ **User Tier Management** - Free/Pro  
✅ **Error Handling** - Edge cases  
✅ **Security** - Input validation, rate limiting  

---

## 🏗️ **Test Architecture**

### **Test Organization**

```
backend/tests/
├── conftest.py                      # Shared fixtures and configuration
├── pytest.ini                       # Pytest settings
├── test_models.py                   # Database model tests
├── test_services_router.py          # Conversation routing logic
├── test_services_renderer.py        # Document generation
├── test_services_payments.py        # Payment and tier management
├── test_api_webhook.py              # API endpoint tests
├── test_integration.py              # End-to-end integration tests
├── test_pdf_generation.py           # PDF rendering (existing)
├── test_resume_flow.py              # Resume flow (existing)
└── test_router.py                   # Router helpers (existing)
```

### **Test Layers**

1. **Unit Tests** - Individual functions and classes
2. **Integration Tests** - Multiple components working together
3. **API Tests** - HTTP endpoints and webhooks
4. **End-to-End Tests** - Complete user workflows

---

## 🚀 **Running Tests**

### **Prerequisites**

```bash
cd backend
poetry install --with dev
```

### **Run All Tests**

```bash
pytest
```

### **Run Specific Test Files**

```bash
# Models
pytest tests/test_models.py

# Router service
pytest tests/test_services_router.py

# Integration tests
pytest tests/test_integration.py

# API endpoints
pytest tests/test_api_webhook.py
```

### **Run Tests by Marker**

```bash
# Unit tests only
pytest -m unit

# Integration tests
pytest -m integration

# API tests
pytest -m api

# Fast tests only (exclude slow)
pytest -m "not slow"
```

### **Run with Coverage**

```bash
# Generate coverage report
pytest --cov=app --cov-report=html --cov-report=term

# View HTML coverage report
# Open htmlcov/index.html in browser
```

### **Run Specific Test**

```bash
# Run single test function
pytest tests/test_models.py::TestUserModel::test_create_user

# Run test class
pytest tests/test_models.py::TestUserModel

# Run tests matching pattern
pytest -k "test_create"
```

### **Verbose Output**

```bash
# Detailed output
pytest -v

# Very detailed with print statements
pytest -v -s

# Show local variables on failure
pytest -v -l
```

---

## 📝 **Test Categories**

### **1. Model Tests** (`test_models.py`)

**Purpose**: Validate database models, relationships, and constraints

**Key Tests**:
- ✅ User creation and uniqueness
- ✅ Job lifecycle and status transitions
- ✅ Message tracking
- ✅ Payment records
- ✅ Cascade deletes
- ✅ JSON field handling
- ✅ Relationship integrity

**Critical Scenarios**:
- Duplicate telegram_user_id handling
- Foreign key constraints
- Default values
- Special characters in data

---

### **2. Router Service Tests** (`test_services_router.py`)

**Purpose**: Test conversation flow logic and state management

**Key Tests**:
- ✅ Type inference (resume/CV/cover)
- ✅ Welcome and greeting handling
- ✅ Basics collection and validation
- ✅ Target role collection
- ✅ Experience gathering (multiple entries)
- ✅ Education collection
- ✅ AI skills generation and selection
- ✅ Summary generation
- ✅ Admin authentication
- ✅ Payment bypass for testing
- ✅ Reset and help commands

**Critical Scenarios**:
- Invalid input formats
- Empty messages
- Special characters
- Very long messages
- State transitions
- Error recovery

---

### **3. Renderer Tests** (`test_services_renderer.py`)

**Purpose**: Test DOCX document generation

**Key Tests**:
- ✅ Resume rendering (all templates)
- ✅ CV rendering (all templates)
- ✅ Cover letter rendering
- ✅ Content validation
- ✅ Special character handling
- ✅ Long content handling
- ✅ Missing optional fields
- ✅ Multiple experiences/education

**Critical Scenarios**:
- Minimal data documents
- Maximum data documents (10+ experiences)
- Special characters (José, O'Brien, etc.)
- Empty lists
- Missing required fields

---

### **4. Payment Tests** (`test_services_payments.py`)

**Purpose**: Test payment logic and user tier management

**Key Tests**:
- ✅ Free tier limits
- ✅ Pro tier unlimited access
- ✅ Per-role generation limits
- ✅ Payment link generation
- ✅ Upgrade payment processing
- ✅ Payment bypass (testing)
- ✅ Generation count tracking

**Critical Scenarios**:
- Free user hits limit
- Pro user after upgrade
- Multiple roles tracking
- Payment API failures
- Invalid references

---

### **5. API Tests** (`test_api_webhook.py`)

**Purpose**: Test HTTP endpoints and webhooks

**Key Tests**:
- ✅ Telegram webhook message handling
- ✅ Telegram callback queries (buttons)
- ✅ Document upload handling
- ✅ Paystack payment webhooks
- ✅ Health check endpoints
- ✅ Rate limiting
- ✅ Security (POST only, signatures)
- ✅ Error handling

**Critical Scenarios**:
- Invalid payloads
- Missing fields
- Duplicate messages (idempotency)
- Rate limit enforcement
- Internal errors

---

### **6. Integration Tests** (`test_integration.py`)

**Purpose**: Test complete workflows end-to-end

**Key Tests**:
- ✅ Full resume creation flow (greeting → document)
- ✅ CV creation flow
- ✅ Cover letter flow
- ✅ Resume with AI skills
- ✅ Payment upgrade flow (free → pro)
- ✅ Document generation for all types
- ✅ Database cascades
- ✅ Error recovery (reset, invalid input)
- ✅ Concurrent users
- ✅ System limits (max experiences)

**Critical Scenarios**:
- Complete user journey
- Multiple document types
- Payment integration
- Concurrent operations
- Long-running flows

---

## 🔧 **Test Fixtures**

### **Database Fixtures** (from `conftest.py`)

- `db_engine` - In-memory SQLite database
- `db_session` - Database session for tests
- `test_user` - Standard free tier user
- `pro_user` - Premium tier user
- `test_job` - Sample job in "collecting" state
- `payment_record` - Sample payment record

### **Data Fixtures**

- `sample_resume_data` - Complete resume data
- `sample_cv_data` - Complete CV data
- `sample_cover_letter_data` - Complete cover letter data

### **Mock Fixtures**

- `mock_ai_service` - Mocked AI service
- `mock_telegram_service` - Mocked Telegram API
- `mock_pdf_renderer` - Mocked PDF renderer
- `mock_storage` - Mocked storage service

---

## 🎯 **Testing Best Practices**

### **1. Test Isolation**

Each test is independent and doesn't rely on other tests:

```python
def test_create_user(db_session):
    """Test user creation"""
    user = User(telegram_user_id="123")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None
```

### **2. Descriptive Names**

Test names clearly describe what they test:

```python
def test_free_tier_limit_reached(db_session, test_user):
    """Test free user hits generation limit"""
    # ...
```

### **3. AAA Pattern** (Arrange, Act, Assert)

```python
def test_example(db_session):
    # Arrange - Set up test data
    user = User(telegram_user_id="123")
    db_session.add(user)
    db_session.commit()
    
    # Act - Perform action
    user.tier = "pro"
    db_session.commit()
    
    # Assert - Verify result
    assert user.tier == "pro"
```

### **4. Mock External Dependencies**

```python
@patch('app.services.ai.generate_skills')
async def test_ai_skills(mock_ai, db_session):
    mock_ai.return_value = ["Python", "SQL"]
    # Test uses mock instead of real AI call
```

### **5. Test Edge Cases**

```python
def test_empty_input(db_session):
    """Test handling of empty input"""
    result = function("")
    assert result is not None
```

---

## 🐛 **Testing for Common Issues**

### **Security Tests**

```python
def test_sql_injection_prevention(db_session):
    """Test SQL injection is prevented"""
    malicious = "'; DROP TABLE users; --"
    user = User(telegram_user_id=malicious)
    # Should not execute SQL
```

### **Concurrency Tests**

```python
async def test_concurrent_users(db_session):
    """Test multiple users simultaneously"""
    for i in range(10):
        await handle_inbound(db_session, f"user_{i}", "/start")
```

### **Performance Tests**

```python
def test_large_document_generation(db_session):
    """Test rendering with 20+ experiences"""
    data = {"experiences": [...]}  # Many entries
    # Should complete in reasonable time
```

---

## 📈 **Coverage Reports**

### **Generate Coverage**

```bash
pytest --cov=app --cov-report=html
```

### **View Coverage**

```bash
# Open in browser
start htmlcov/index.html  # Windows
open htmlcov/index.html   # Mac
xdg-open htmlcov/index.html  # Linux
```

### **Coverage Goals**

- **Critical Business Logic**: 90%+
- **API Endpoints**: 85%+
- **Models**: 80%+
- **Utilities**: 70%+
- **Overall**: 80%+

---

## 🔄 **CI/CD Integration**

### **GitHub Actions** (Example)

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install --with dev
      - name: Run tests
        run: poetry run pytest --cov=app
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## 🎓 **Testing Strategy Summary**

### **What We Test**

✅ **Business Logic** - Conversation flows, state management  
✅ **Data Layer** - Models, relationships, constraints  
✅ **Integration** - Component interactions  
✅ **API** - Webhooks, endpoints, security  
✅ **Documents** - Rendering, formatting, content  
✅ **Payments** - Limits, upgrades, tracking  
✅ **Edge Cases** - Errors, invalid input, boundaries  

### **What We Mock**

🔀 **External APIs** - AI services, Paystack  
🔀 **Telegram Bot API** - Message sending  
🔀 **File System** - Storage operations (when appropriate)  

### **What We Don't Test**

❌ **Third-party Libraries** - python-docx, SQLAlchemy internals  
❌ **Framework Code** - FastAPI, Pydantic internals  
❌ **External Services** - Actual API calls (use mocks)  

---

## 🚨 **Known Gaps & Future Improvements**

### **Current Gaps**

1. **PDF Rendering Tests** - Only basic tests exist, need comprehensive validation
2. **Rate Limiting Tests** - Need more thorough concurrent request testing
3. **Storage Service** - Not tested (not integrated yet)
4. **Error Monitor** - Minimal testing
5. **Analytics Service** - Basic testing only

### **Future Improvements**

1. **Performance Tests** - Add benchmarking for slow operations
2. **Load Tests** - Test with realistic concurrent user load
3. **Security Tests** - Add penetration testing scenarios
4. **Mutation Testing** - Use `mutpy` to verify test quality
5. **E2E Browser Tests** - Add Selenium/Playwright for full UI testing

---

## 💡 **Writing New Tests**

### **Template for New Test**

```python
"""
Tests for [component name]
[Brief description of what this file tests]
"""
import pytest
from app.models import User, Job


class TestNewFeature:
    """Test [feature name]"""

    def test_basic_case(self, db_session):
        """Test [specific scenario]"""
        # Arrange
        user = User(telegram_user_id="123")
        db_session.add(user)
        db_session.commit()
        
        # Act
        result = perform_action(user)
        
        # Assert
        assert result is not None
        assert result.status == "success"

    def test_edge_case(self, db_session):
        """Test [edge case scenario]"""
        # Test edge case
```

### **Checklist for New Tests**

- [ ] Descriptive test name
- [ ] Clear docstring
- [ ] AAA pattern (Arrange, Act, Assert)
- [ ] Uses appropriate fixtures
- [ ] Tests both success and failure paths
- [ ] Includes edge cases
- [ ] Mocks external dependencies
- [ ] Cleans up resources (if needed)

---

## 📚 **Additional Resources**

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/14/testing.html)

---

## ✅ **Test Execution Checklist**

### **Before Committing**

- [ ] Run all tests: `pytest`
- [ ] Check coverage: `pytest --cov=app`
- [ ] Fix any failures
- [ ] Update tests if business logic changed

### **Before Deploying**

- [ ] Run full test suite with coverage
- [ ] Run integration tests: `pytest -m integration`
- [ ] Check for flaky tests
- [ ] Verify test database is isolated
- [ ] Review coverage report

---

**Last Updated**: January 13, 2026  
**Maintained By**: Development Team  
**Questions**: See project README or contact maintainers
