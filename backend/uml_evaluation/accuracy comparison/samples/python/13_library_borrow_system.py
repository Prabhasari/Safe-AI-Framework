# 14_library_borrow_system.py
# Library Book Borrowing System
# Sample for UML Diagram Accuracy Evaluation

from typing import List, Optional
from datetime import datetime


# ── Domain Models ─────────────────────────────────────────────────────────────

class Book:
    def __init__(self, book_id: str, title: str, author: str, isbn: str):
        self.book_id: str = book_id
        self.title: str = title
        self.author: str = author
        self.isbn: str = isbn
        self.available: bool = True

    def mark_borrowed(self):
        self.available = False

    def mark_returned(self):
        self.available = True


class Member:
    def __init__(self, member_id: str, name: str, email: str):
        self.member_id: str = member_id
        self.name: str = name
        self.email: str = email
        self.active: bool = True

    def deactivate(self):
        self.active = False


class BorrowRecord:
    def __init__(self, record_id: str, book_id: str, member_id: str):
        self.record_id: str = record_id
        self.book_id: str = book_id
        self.member_id: str = member_id
        self.borrow_date: datetime = datetime.now()
        self.return_date: Optional[datetime] = None
        self.returned: bool = False

    def mark_returned(self):
        self.returned = True
        self.return_date = datetime.now()


# ── Repository ────────────────────────────────────────────────────────────────

class BookRepository:
    def __init__(self):
        self._store: dict = {}

    def save(self, book: Book):
        self._store[book.book_id] = book

    def find_by_id(self, book_id: str) -> Optional[Book]:
        return self._store.get(book_id)

    def find_available(self) -> List[Book]:
        return [b for b in self._store.values() if b.available]


class BorrowRepository:
    def __init__(self):
        self._store: dict = {}

    def save(self, record: BorrowRecord):
        self._store[record.record_id] = record

    def find_by_member(self, member_id: str) -> List[BorrowRecord]:
        return [r for r in self._store.values() if r.member_id == member_id]

    def find_active(self) -> List[BorrowRecord]:
        return [r for r in self._store.values() if not r.returned]


# ── Service ───────────────────────────────────────────────────────────────────

class BorrowService:
    def __init__(self, book_repository: BookRepository,
                 borrow_repository: BorrowRepository):
        self.book_repository: BookRepository = book_repository
        self.borrow_repository: BorrowRepository = borrow_repository

    def borrow_book(self, record_id: str, book_id: str, member_id: str) -> bool:
        book = self.book_repository.find_by_id(book_id)
        if book is None or not book.available:
            return False
        book.mark_borrowed()
        self.book_repository.save(book)
        record = BorrowRecord(record_id, book_id, member_id)
        self.borrow_repository.save(record)
        return True

    def return_book(self, book_id: str, member_id: str) -> bool:
        book = self.book_repository.find_by_id(book_id)
        if book is None:
            return False
        records = self.borrow_repository.find_by_member(member_id)
        for record in records:
            if record.book_id == book_id and not record.returned:
                record.mark_returned()
                self.borrow_repository.save(record)
                book.mark_returned()
                self.book_repository.save(book)
                return True
        return False

    def get_member_borrows(self, member_id: str) -> List[BorrowRecord]:
        return self.borrow_repository.find_by_member(member_id)


# ── Controller ────────────────────────────────────────────────────────────────

class LibraryController:
    def __init__(self, borrow_service: BorrowService):
        self.borrow_service: BorrowService = borrow_service

    def borrow(self, record_id: str, book_id: str, member_id: str) -> dict:
        success = self.borrow_service.borrow_book(record_id, book_id, member_id)
        return {"success": success, "book_id": book_id}

    def return_book(self, book_id: str, member_id: str) -> dict:
        success = self.borrow_service.return_book(book_id, member_id)
        return {"success": success, "book_id": book_id}

    def get_history(self, member_id: str) -> dict:
        records = self.borrow_service.get_member_borrows(member_id)
        return {"member_id": member_id, "total": len(records)}