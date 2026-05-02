# ground_truth_14_library_borrow_system.py
# Hand-verified ground truth for UML Diagram Accuracy Evaluation
# Sample: 14_library_borrow_system.py | Language: Python
# Architecture: 3-layer (Controller -> Service -> Repository)

# ── CLASS DIAGRAM ─────────────────────────────────────────────────────────────

CLASSES = [
    "Book",
    "Member",
    "BorrowRecord",
    "BookRepository",
    "BorrowRepository",
    "BorrowService",
    "LibraryController",
]

FIELDS = {
    "Book": [
        "book_id", "title", "author", "isbn", "available",
    ],
    "Member": [
        "member_id", "name", "email", "active",
    ],
    "BorrowRecord": [
        "record_id", "book_id", "member_id",
        "borrow_date", "return_date", "returned",
    ],
    "BookRepository": [
        "_store",
    ],
    "BorrowRepository": [
        "_store",
    ],
    "BorrowService": [
        "book_repository", "borrow_repository",
    ],
    "LibraryController": [
        "borrow_service",
    ],
}

METHODS = {
    "Book": [
        "mark_borrowed", "mark_returned",
    ],
    "Member": [
        "deactivate",
    ],
    "BorrowRecord": [
        "mark_returned",
    ],
    "BookRepository": [
        "save", "find_by_id", "find_available",
    ],
    "BorrowRepository": [
        "save", "find_by_member", "find_active",
    ],
    "BorrowService": [
        "borrow_book", "return_book", "get_member_borrows",
    ],
    "LibraryController": [
        "borrow", "return_book", "get_history",
    ],
}

ASSOCIATES = [
    ("LibraryController", "BorrowService"),
    ("BorrowService",     "BookRepository"),
    ("BorrowService",     "BorrowRepository"),
]

DEPENDS_ON = [
    ("BorrowService",     "Book"),
    ("BorrowService",     "BorrowRecord"),
    ("LibraryController", "BorrowRecord"),
]

# ── PACKAGE DIAGRAM ───────────────────────────────────────────────────────────

PACKAGES = [
    "domain",
    "repository",
    "service",
    "controller",
]

PACKAGE_CONTENTS = {
    "domain":     ["Book", "Member", "BorrowRecord"],
    "repository": ["BookRepository", "BorrowRepository"],
    "service":    ["BorrowService"],
    "controller": ["LibraryController"],
}

PACKAGE_DEPENDENCIES = [
    ("controller", "service"),
    ("service",    "repository"),
    ("service",    "domain"),
    ("repository", "domain"),
]

# ── SEQUENCE DIAGRAM ──────────────────────────────────────────────────────────

SEQUENCE_TITLE = "Borrow Book Flow"

SEQUENCE_PARTICIPANTS = [
    "Client",
    "LibraryController",
    "BorrowService",
    "BookRepository",
    "BorrowRepository",
]

SEQUENCE_MESSAGES = [
    ("Client",            "LibraryController", "borrow(record_id, book_id, member_id)"),
    ("LibraryController", "BorrowService",     "borrow_book(record_id, book_id, member_id)"),
    ("BorrowService",     "BookRepository",    "find_by_id(book_id)"),
    ("BookRepository",    "BorrowService",     "return book"),
    ("BorrowService",     "Book",              "mark_borrowed()"),
    ("BorrowService",     "BookRepository",    "save(book)"),
    ("BorrowService",     "BorrowRecord",      "new BorrowRecord(...)"),
    ("BorrowService",     "BorrowRepository",  "save(record)"),
    ("BorrowService",     "LibraryController", "return True"),
    ("LibraryController", "Client",            "return {success: True}"),
]

# ── COMPONENT DIAGRAM ─────────────────────────────────────────────────────────

COMPONENTS = [
    "LibraryController",
    "BorrowService",
    "BookRepository",
    "BorrowRepository",
]

INTERFACES = [
    "IBookRepository",
    "IBorrowRepository",
]

COMPONENT_CONNECTIONS = [
    ("LibraryController", "BorrowService"),
    ("BorrowService",     "IBookRepository"),
    ("BorrowService",     "IBorrowRepository"),
    ("BookRepository",    "IBookRepository"),
    ("BorrowRepository",  "IBorrowRepository"),
]

# ── ACTIVITY DIAGRAM ──────────────────────────────────────────────────────────

ACTIVITY_TITLE = "Borrow Book Activity"

SWIMLANES = [
    "Client",
    "LibraryController",
    "BorrowService",
    "BookRepository",
]

ACTIONS = [
    "Receive borrow request",
    "Call borrow_book()",
    "Find book by ID",
    "Check availability",
    "Mark book as borrowed",
    "Save book",
    "Create BorrowRecord",
    "Save record",
    "Return result",
]

DECISIONS = [
    "Book exists?",
    "Book available?",
]

ACTIVITY_START = "Receive borrow request"
ACTIVITY_END   = "Return result"