# ground_truth_11.py
# Hand-verified ground truth for 11_library_management.java

SAMPLE   = "11_library_management.java"
LANGUAGE = "java"

CLASS_GT = {
    "classes": {
        "Book", "Member", "BorrowRecord", "BookStatus",
        "IBookRepository", "IMemberRepository", "IBorrowRepository",
        "BookRepository", "MemberRepository", "BorrowRepository",
        "BookService", "BorrowService", "LibraryController", "DatabaseConnection"
    },
    "fields": {
        "Book.bookId", "Book.title", "Book.author", "Book.isbn",
        "Book.status", "Book.totalCopies", "Book.availableCopies",
        "Member.memberId", "Member.fullName", "Member.email",
        "Member.phone", "Member.active", "Member.borrowedCount",
        "BorrowRecord.recordId", "BorrowRecord.book", "BorrowRecord.member",
        "BorrowRecord.borrowDate", "BorrowRecord.dueDate",
        "BorrowRecord.returnDate", "BorrowRecord.returned", "BorrowRecord.fineAmount",
        "BookRepository.connection", "MemberRepository.connection", "BorrowRepository.connection",
        "BookService.bookRepository",
        "BorrowService.borrowRepository", "BorrowService.bookRepository",
        "BorrowService.memberRepository",
        "LibraryController.bookService", "LibraryController.borrowService",
        "DatabaseConnection.url", "DatabaseConnection.username",
        "DatabaseConnection.password", "DatabaseConnection.connected", "DatabaseConnection.poolSize",
    },
    "methods": {
        "Book.getBookId", "Book.getTitle", "Book.getAuthor", "Book.getIsbn",
        "Book.getStatus", "Book.setStatus", "Book.getAvailableCopies",
        "Book.decrementCopies", "Book.incrementCopies", "Book.isAvailable",
        "Member.getMemberId", "Member.getFullName", "Member.getEmail",
        "Member.isActive", "Member.getBorrowedCount",
        "Member.incrementBorrowed", "Member.decrementBorrowed",
        "BorrowRecord.getRecordId", "BorrowRecord.getBook", "BorrowRecord.getMember",
        "BorrowRecord.getDueDate", "BorrowRecord.isReturned", "BorrowRecord.markReturned",
        "BorrowRecord.getFineAmount", "BorrowRecord.setFineAmount",
        "IBookRepository.findById", "IBookRepository.findAll",
        "IBookRepository.findByAuthor", "IBookRepository.findAvailable",
        "IBookRepository.save", "IBookRepository.delete",
        "IMemberRepository.findById", "IMemberRepository.findAll",
        "IMemberRepository.findByEmail", "IMemberRepository.save", "IMemberRepository.delete",
        "IBorrowRepository.findById", "IBorrowRepository.findByMember",
        "IBorrowRepository.findByBook", "IBorrowRepository.findOverdue", "IBorrowRepository.save",
        "BookRepository.findById", "BookRepository.findAll", "BookRepository.findByAuthor",
        "BookRepository.findAvailable", "BookRepository.save", "BookRepository.delete",
        "MemberRepository.findById", "MemberRepository.findAll",
        "MemberRepository.findByEmail", "MemberRepository.save", "MemberRepository.delete",
        "BorrowRepository.findById", "BorrowRepository.findByMember",
        "BorrowRepository.findByBook", "BorrowRepository.findOverdue", "BorrowRepository.save",
        "BookService.getBook", "BookService.getAllBooks", "BookService.searchByAuthor",
        "BookService.getAvailableBooks", "BookService.addBook",
        "BookService.removeBook", "BookService.checkAvailability",
        "BorrowService.borrowBook", "BorrowService.returnBook",
        "BorrowService.getMemberHistory", "BorrowService.getOverdueRecords",
        "BorrowService.calculateFine",
        "LibraryController.handleGetBook", "LibraryController.handleGetAvailable",
        "LibraryController.handleBorrow", "LibraryController.handleReturn",
        "LibraryController.handleGetOverdue", "LibraryController.handleCalculateFine",
        "DatabaseConnection.connect", "DatabaseConnection.disconnect",
        "DatabaseConnection.isConnected", "DatabaseConnection.getPoolSize",
    },
    "relationships": {
        ("implements", "BookRepository",   "IBookRepository"),
        ("implements", "MemberRepository", "IMemberRepository"),
        ("implements", "BorrowRepository", "IBorrowRepository"),
        ("associates", "BookRepository",   "DatabaseConnection"),
        ("associates", "MemberRepository", "DatabaseConnection"),
        ("associates", "BorrowRepository", "DatabaseConnection"),
        ("associates", "BookService",      "IBookRepository"),
        ("associates", "BorrowService",    "IBorrowRepository"),
        ("associates", "BorrowService",    "IBookRepository"),
        ("associates", "BorrowService",    "IMemberRepository"),
        ("associates", "LibraryController","BookService"),
        ("associates", "LibraryController","BorrowService"),
        ("associates", "BorrowRecord",     "Book"),
        ("associates", "BorrowRecord",     "Member"),
        ("depends_on", "BookService",      "Book"),
        ("depends_on", "BorrowService",    "BorrowRecord"),
        ("depends_on", "BorrowService",    "Book"),
        ("depends_on", "LibraryController","BorrowRecord"),
        ("depends_on", "LibraryController","Book"),
    }
}
CLASS_VERIFIED = True

PACKAGE_GT = {
    "packages": set(),
    "members": {
        "Book", "Member", "BorrowRecord", "BookStatus",
        "IBookRepository", "IMemberRepository", "IBorrowRepository",
        "BookRepository", "MemberRepository", "BorrowRepository",
        "BookService", "BorrowService", "LibraryController", "DatabaseConnection"
    },
    "dependencies": {
        "BookRepository->IBookRepository",
        "MemberRepository->IMemberRepository",
        "BorrowRepository->IBorrowRepository",
        "BookRepository->DatabaseConnection",
        "BookService->IBookRepository",
        "BorrowService->IBorrowRepository",
        "LibraryController->BookService",
        "LibraryController->BorrowService",
    }
}
PACKAGE_VERIFIED = True

SEQUENCE_GT = {
    "participants": {
        "LibraryController", "BookService", "BorrowService",
        "IBookRepository", "IBorrowRepository",
    },
    "key_messages": {
        "LibraryController->BookService:checkAvailability",
        "LibraryController->BorrowService:borrowBook",
        "BorrowService->IBookRepository:findById",
        "BorrowService->IBorrowRepository:save",
        "LibraryController->BorrowService:returnBook",
        "LibraryController->BorrowService:calculateFine",
    }
}
SEQUENCE_VERIFIED = True

COMPONENT_GT = {
    "components": {
        "LibraryController", "BookService", "BorrowService",
        "BookRepository", "MemberRepository", "BorrowRepository", "DatabaseConnection"
    },
    "interfaces": {
        "IBookRepository", "IMemberRepository", "IBorrowRepository",
        "BookService", "BorrowService",
    },
    "connections": {
        "LibraryController->BookService",
        "LibraryController->BorrowService",
        "BorrowService->IBookRepository",
        "BorrowService->IBorrowRepository",
        "BorrowService->IMemberRepository",
        "BookService->IBookRepository",
        "BookRepository->DatabaseConnection",
    }
}
COMPONENT_VERIFIED = True

ACTIVITY_GT = {
    "actions": {
        "handleBorrow", "borrowBook", "checkAvailability",
        "findById", "save", "decrementCopies",
        "handleReturn", "returnBook", "markReturned", "incrementCopies",
        "calculateFine", "handleCalculateFine",
    },
    "decisions": {
        "more items",
    },
    "swimlanes": {
        "LibraryController", "BookService", "BorrowService",
        "IBookRepository", "IBorrowRepository",
    }
}
ACTIVITY_VERIFIED = True