"""Assistant bot with an address book, phones and birthdays.

The address book is saved to disk with pickle on exit
and loaded back on the next start.
"""

import pickle
from collections import UserDict
from datetime import date, datetime, timedelta
from functools import wraps

DATE_FORMAT = "%d.%m.%Y"


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------

class Field:
    """Base class for all record fields."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)


class Name(Field):
    """Contact name (required)."""

    def __init__(self, value):
        if not value or not value.strip():
            raise ValueError("Name cannot be empty.")
        super().__init__(value.strip())


class Phone(Field):
    """Phone number: exactly 10 digits."""

    def __init__(self, value):
        if not (isinstance(value, str) and value.isdigit() and len(value) == 10):
            raise ValueError("Phone number must contain exactly 10 digits.")
        super().__init__(value)


class Birthday(Field):
    """Birthday in DD.MM.YYYY format, stored as a date object."""

    def __init__(self, value):
        try:
            birthday = datetime.strptime(value, DATE_FORMAT).date()
        except (ValueError, TypeError):
            raise ValueError("Invalid date format. Use DD.MM.YYYY")
        if birthday > date.today():
            raise ValueError("Birthday cannot be in the future.")
        super().__init__(birthday)

    def __str__(self):
        return self.value.strftime(DATE_FORMAT)


# ---------------------------------------------------------------------------
# Record and AddressBook
# ---------------------------------------------------------------------------

class Record:
    """One contact: a name, a list of phones and an optional birthday."""

    def __init__(self, name):
        self.name = Name(name)
        self.phones = []
        self.birthday = None

    def add_phone(self, phone):
        if self.find_phone(phone):
            raise ValueError(f"Phone {phone} already exists for {self.name}.")
        self.phones.append(Phone(phone))

    def remove_phone(self, phone):
        phone_obj = self.find_phone(phone)
        if phone_obj is None:
            raise ValueError(f"Phone {phone} not found for {self.name}.")
        self.phones.remove(phone_obj)

    def edit_phone(self, old_phone, new_phone):
        phone_obj = self.find_phone(old_phone)
        if phone_obj is None:
            raise ValueError(f"Phone {old_phone} not found for {self.name}.")
        # Validate the new number before replacing the old one
        new_phone_obj = Phone(new_phone)
        self.phones[self.phones.index(phone_obj)] = new_phone_obj

    def find_phone(self, phone):
        for phone_obj in self.phones:
            if phone_obj.value == phone:
                return phone_obj
        return None

    def add_birthday(self, birthday):
        # Only one birthday per contact: a new one replaces the old one
        self.birthday = Birthday(birthday)

    def __str__(self):
        phones = "; ".join(p.value for p in self.phones) or "no phones"
        birthday = f", birthday: {self.birthday}" if self.birthday else ""
        return f"Contact name: {self.name.value}, phones: {phones}{birthday}"


class AddressBook(UserDict):
    """Stores records by contact name."""

    def add_record(self, record):
        self.data[record.name.value] = record

    def find(self, name):
        return self.data.get(name)

    def delete(self, name):
        self.data.pop(name, None)

    def get_upcoming_birthdays(self, days=7):
        """Return contacts to congratulate in the next `days` days (today included).

        If a birthday falls on Saturday or Sunday, the congratulation
        moves to the following Monday.
        Result: list of {"name": ..., "congratulation_date": "DD.MM.YYYY"}.
        """
        today = date.today()
        upcoming = []

        for record in self.data.values():
            if record.birthday is None:
                continue

            birthday_this_year = _birthday_in_year(record.birthday.value, today.year)
            if birthday_this_year < today:
                birthday_this_year = _birthday_in_year(record.birthday.value, today.year + 1)

            if (birthday_this_year - today).days < days:
                congratulation_date = birthday_this_year
                if congratulation_date.weekday() == 5:      # Saturday
                    congratulation_date += timedelta(days=2)
                elif congratulation_date.weekday() == 6:    # Sunday
                    congratulation_date += timedelta(days=1)

                upcoming.append({
                    "name": record.name.value,
                    "congratulation_date": congratulation_date.strftime(DATE_FORMAT),
                })

        upcoming.sort(key=lambda item: datetime.strptime(item["congratulation_date"], DATE_FORMAT))
        return upcoming


def _birthday_in_year(birthday, year):
    """Birthday date in the given year (29 February -> 28 February in non-leap years)."""
    try:
        return birthday.replace(year=year)
    except ValueError:
        return birthday.replace(year=year, day=28)


# ---------------------------------------------------------------------------
# Bot: error decorator, parser and command handlers
# ---------------------------------------------------------------------------

def input_error(func):
    """Turn input errors into readable messages instead of crashing the bot."""

    @wraps(func)
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as error:
            # Our own validation messages, or wrong number of arguments
            message = str(error)
            if "unpack" in message:
                return "Not enough arguments. Type the command with all its arguments."
            return message
        except KeyError:
            return "Contact not found."
        except IndexError:
            return "Enter the contact name."

    return inner


def parse_input(user_input):
    parts = user_input.split()
    if not parts:
        return ("",)
    cmd, *args = parts
    return cmd.strip().lower(), *args


@input_error
def add_contact(args, book: AddressBook):
    name, phone, *_ = args
    record = book.find(name)
    message = "Contact updated."
    if record is None:
        record = Record(name)
        book.add_record(record)
        message = "Contact added."
    if phone:
        try:
            record.add_phone(phone)
        except ValueError:
            # Don't keep an empty new contact if the phone was invalid
            if message == "Contact added.":
                book.delete(name)
            raise
    return message


@input_error
def change_contact(args, book: AddressBook):
    name, old_phone, new_phone, *_ = args
    record = book.find(name)
    if record is None:
        raise KeyError(name)
    record.edit_phone(old_phone, new_phone)
    return "Contact updated."


@input_error
def show_phone(args, book: AddressBook):
    name = args[0]
    record = book.find(name)
    if record is None:
        raise KeyError(name)
    if not record.phones:
        return f"{name} has no phones."
    return f"{name}: " + "; ".join(p.value for p in record.phones)


@input_error
def show_all(book: AddressBook):
    if not book:
        return "Address book is empty."
    return "\n".join(str(record) for record in book.values())


@input_error
def add_birthday(args, book: AddressBook):
    name, birthday, *_ = args
    record = book.find(name)
    if record is None:
        raise KeyError(name)
    record.add_birthday(birthday)
    return "Birthday added."


@input_error
def show_birthday(args, book: AddressBook):
    name = args[0]
    record = book.find(name)
    if record is None:
        raise KeyError(name)
    if record.birthday is None:
        return f"{name} has no birthday saved."
    return f"{name}: {record.birthday}"


@input_error
def birthdays(args, book: AddressBook):
    upcoming = book.get_upcoming_birthdays()
    if not upcoming:
        return "No birthdays in the next 7 days."
    lines = [f"{item['congratulation_date']}: {item['name']}" for item in upcoming]
    return "Upcoming birthdays:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Saving and loading the address book (pickle)
# ---------------------------------------------------------------------------

DATA_FILE = "addressbook.pkl"


def save_data(book, filename=DATA_FILE):
    """Serialize the address book to a file."""
    with open(filename, "wb") as f:
        pickle.dump(book, f)


def load_data(filename=DATA_FILE):
    """Load the address book from a file, or return a new one."""
    try:
        with open(filename, "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return AddressBook()  # first start: no file yet
    except (pickle.UnpicklingError, EOFError, AttributeError):
        print("Warning: data file is damaged, starting with an empty address book.")
        return AddressBook()


def main():
    book = load_data()
    print("Welcome to the assistant bot!")
    try:
        run_bot(book)
    except (KeyboardInterrupt, EOFError):
        # Ctrl+C / Ctrl+D: still save the data before leaving
        print("\nGood bye!")
    finally:
        save_data(book)  # always called before the program ends


def run_bot(book):
    """Main request-response loop."""
    while True:
        user_input = input("Enter a command: ")
        command, *args = parse_input(user_input)

        if command in ["close", "exit"]:
            print("Good bye!")
            break

        elif command == "hello":
            print("How can I help you?")

        elif command == "add":
            print(add_contact(args, book))

        elif command == "change":
            print(change_contact(args, book))

        elif command == "phone":
            print(show_phone(args, book))

        elif command == "all":
            print(show_all(book))

        elif command == "add-birthday":
            print(add_birthday(args, book))

        elif command == "show-birthday":
            print(show_birthday(args, book))

        elif command == "birthdays":
            print(birthdays(args, book))

        else:
            print("Invalid command.")


if __name__ == "__main__":
    main()
