// SAMPLE 11 — java_library_management_system
// COMPLEXITY: high
// ARCHITECTURE: 4-layer (Controller -> Service -> Repository -> DB)
// DESIGNED FOR: rich output across all 5 diagram types
// Features: interface + implementation, method call chains,
//           multiple associations, enum, exception handling pattern

import java.util.List;
import java.util.Optional;

// ── Domain Models ──────────────────────────────────────────────────────────

enum BookStatus {
    AVAILABLE, BORROWED, RESERVED, LOST
}

class Book {
    private String bookId;
    private String title;
    private String author;
    private String isbn;
    private BookStatus status;
    private int totalCopies;
    private int availableCopies;

    public String getBookId() { return bookId; }
    public String getTitle() { return title; }
    public String getAuthor() { return author; }
    public String getIsbn() { return isbn; }
    public BookStatus getStatus() { return status; }
    public void setStatus(BookStatus status) { this.status = status; }
    public int getAvailableCopies() { return availableCopies; }
    public void decrementCopies() { this.availableCopies--; }
    public void incrementCopies() { this.availableCopies++; }
    public boolean isAvailable() { return availableCopies > 0; }
}

class Member {
    private String memberId;
    private String fullName;
    private String email;
    private String phone;
    private boolean active;
    private int borrowedCount;

    public String getMemberId() { return memberId; }
    public String getFullName() { return fullName; }
    public String getEmail() { return email; }
    public boolean isActive() { return active; }
    public int getBorrowedCount() { return borrowedCount; }
    public void incrementBorrowed() { this.borrowedCount++; }
    public void decrementBorrowed() { this.borrowedCount--; }
}

class BorrowRecord {
    private String recordId;
    private Book book;
    private Member member;
    private String borrowDate;
    private String dueDate;
    private String returnDate;
    private boolean returned;
    private double fineAmount;

    public String getRecordId() { return recordId; }
    public Book getBook() { return book; }
    public Member getMember() { return member; }
    public String getDueDate() { return dueDate; }
    public boolean isReturned() { return returned; }
    public void markReturned(String returnDate) {
        this.returned = true;
        this.returnDate = returnDate;
    }
    public double getFineAmount() { return fineAmount; }
    public void setFineAmount(double amount) { this.fineAmount = amount; }
}

// ── Repository Layer ───────────────────────────────────────────────────────

interface IBookRepository {
    Optional<Book> findById(String bookId);
    List<Book> findAll();
    List<Book> findByAuthor(String author);
    List<Book> findAvailable();
    void save(Book book);
    void delete(String bookId);
}

interface IMemberRepository {
    Optional<Member> findById(String memberId);
    List<Member> findAll();
    Optional<Member> findByEmail(String email);
    void save(Member member);
    void delete(String memberId);
}

interface IBorrowRepository {
    Optional<BorrowRecord> findById(String recordId);
    List<BorrowRecord> findByMember(String memberId);
    List<BorrowRecord> findByBook(String bookId);
    List<BorrowRecord> findOverdue();
    void save(BorrowRecord record);
}

class BookRepository implements IBookRepository {
    private DatabaseConnection connection;

    public Optional<Book> findById(String bookId) { return Optional.empty(); }
    public List<Book> findAll() { return null; }
    public List<Book> findByAuthor(String author) { return null; }
    public List<Book> findAvailable() { return null; }
    public void save(Book book) {}
    public void delete(String bookId) {}
}

class MemberRepository implements IMemberRepository {
    private DatabaseConnection connection;

    public Optional<Member> findById(String memberId) { return Optional.empty(); }
    public List<Member> findAll() { return null; }
    public Optional<Member> findByEmail(String email) { return Optional.empty(); }
    public void save(Member member) {}
    public void delete(String memberId) {}
}

class BorrowRepository implements IBorrowRepository {
    private DatabaseConnection connection;

    public Optional<BorrowRecord> findById(String recordId) { return Optional.empty(); }
    public List<BorrowRecord> findByMember(String memberId) { return null; }
    public List<BorrowRecord> findByBook(String bookId) { return null; }
    public List<BorrowRecord> findOverdue() { return null; }
    public void save(BorrowRecord record) {}
}

// ── Service Layer ──────────────────────────────────────────────────────────

class BookService {
    private IBookRepository bookRepository;

    public Book getBook(String bookId) {
        return bookRepository.findById(bookId).orElse(null);
    }
    public List<Book> getAllBooks() { return bookRepository.findAll(); }
    public List<Book> searchByAuthor(String author) { return bookRepository.findByAuthor(author); }
    public List<Book> getAvailableBooks() { return bookRepository.findAvailable(); }
    public Book addBook(Book book) { bookRepository.save(book); return book; }
    public void removeBook(String bookId) { bookRepository.delete(bookId); }
    public boolean checkAvailability(String bookId) {
        Book book = bookRepository.findById(bookId).orElse(null);
        return book != null && book.isAvailable();
    }
}

class BorrowService {
    private IBorrowRepository borrowRepository;
    private IBookRepository bookRepository;
    private IMemberRepository memberRepository;

    public BorrowRecord borrowBook(String memberId, String bookId) {
        Member member = memberRepository.findById(memberId).orElse(null);
        Book book = bookRepository.findById(bookId).orElse(null);
        if (member == null || book == null || !book.isAvailable()) return null;
        book.decrementCopies();
        member.incrementBorrowed();
        bookRepository.save(book);
        memberRepository.save(member);
        BorrowRecord record = new BorrowRecord();
        borrowRepository.save(record);
        return record;
    }

    public boolean returnBook(String recordId) {
        BorrowRecord record = borrowRepository.findById(recordId).orElse(null);
        if (record == null || record.isReturned()) return false;
        record.markReturned("today");
        record.getBook().incrementCopies();
        record.getMember().decrementBorrowed();
        borrowRepository.save(record);
        bookRepository.save(record.getBook());
        memberRepository.save(record.getMember());
        return true;
    }

    public List<BorrowRecord> getMemberHistory(String memberId) {
        return borrowRepository.findByMember(memberId);
    }

    public List<BorrowRecord> getOverdueRecords() {
        return borrowRepository.findOverdue();
    }

    public double calculateFine(String recordId) {
        BorrowRecord record = borrowRepository.findById(recordId).orElse(null);
        if (record == null) return 0.0;
        double fine = 5.0;
        record.setFineAmount(fine);
        borrowRepository.save(record);
        return fine;
    }
}

// ── Controller Layer ───────────────────────────────────────────────────────
class LibraryController {
    private BookService bookService;
    private BorrowService borrowService;

    public Book handleGetBook(String bookId) {
        return bookService.getBook(bookId);
    }

    public List<Book> handleGetAvailable() {
        return bookService.getAvailableBooks();
    }

    public BorrowRecord handleBorrow(String memberId, String bookId) {
        if (!bookService.checkAvailability(bookId)) return null;
        return borrowService.borrowBook(memberId, bookId);
    }

    public boolean handleReturn(String recordId) {
        return borrowService.returnBook(recordId);
    }

    public List<BorrowRecord> handleGetOverdue() {
        return borrowService.getOverdueRecords();
    }

    public double handleCalculateFine(String recordId) {
        return borrowService.calculateFine(recordId);
    }
}

// ── Infrastructure ─────────────────────────────────────────────────────────

class DatabaseConnection {
    private String url;
    private String username;
    private String password;
    private boolean connected;
    private int poolSize;

    public boolean connect() { this.connected = true; return true; }
    public void disconnect() { this.connected = false; }
    public boolean isConnected() { return connected; }
    public int getPoolSize() { return poolSize; }
}