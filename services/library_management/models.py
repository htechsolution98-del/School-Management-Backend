from django.db import models


class BookCategory(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "library_book_category"

    def __str__(self):
        return self.name


class Author(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "library_author"

    def __str__(self):
        return self.name


class Publisher(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "library_publisher"


class Rack(models.Model):
    number = models.CharField(max_length=50)

    class Meta:
        db_table = "service_library_rack"


class Shelf(models.Model):
    rack = models.ForeignKey(Rack, on_delete=models.CASCADE, related_name="shelves")
    number = models.CharField(max_length=50)

    class Meta:
        db_table = "service_library_shelf"


class Book(models.Model):
    title = models.CharField(max_length=255)
    category = models.ForeignKey(BookCategory, on_delete=models.SET_NULL, null=True)
    author = models.ForeignKey(Author, on_delete=models.SET_NULL, null=True)
    publisher = models.ForeignKey(Publisher, on_delete=models.SET_NULL, null=True)
    isbn = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = "library_book"

    def __str__(self):
        return self.title


class BookCopy(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="copies")
    barcode = models.CharField(max_length=100, unique=True)
    is_available = models.BooleanField(default=True)

    class Meta:
        db_table = "library_book_copy"


class BookIssued(models.Model):
    book_copy = models.ForeignKey(BookCopy, on_delete=models.CASCADE)
    student = models.ForeignKey("student_admission.Student", on_delete=models.CASCADE, null=True, blank=True)
    staff = models.ForeignKey("staff_hr.Staff", on_delete=models.CASCADE, null=True, blank=True)
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "library_book_issued"
