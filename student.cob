
       IDENTIFICATION DIVISION.
       PROGRAM-ID. STUDENT-REPORT.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 STUDENT-NAME PIC A(30).
       01 MARKS-1      PIC 9(3).
       01 MARKS-2      PIC 9(3).
       01 MARKS-3      PIC 9(3).
       01 TOTAL-MARKS  PIC 9(4).
       01 AVERAGE-MARKS PIC 999.99.

       PROCEDURE DIVISION.
       MAIN-PROCEDURE.
           DISPLAY "===== STUDENT REPORT ====="
           DISPLAY "Enter student name:"
           ACCEPT STUDENT-NAME

           DISPLAY "Enter marks for Subject 1:"
           ACCEPT MARKS-1

           DISPLAY "Enter marks for Subject 2:"
           ACCEPT MARKS-2

           DISPLAY "Enter marks for Subject 3:"
           ACCEPT MARKS-3

           COMPUTE TOTAL-MARKS =
               MARKS-1 + MARKS-2 + MARKS-3

           COMPUTE AVERAGE-MARKS =
               TOTAL-MARKS / 3

           DISPLAY " "
           DISPLAY "===== RESULT ====="
           DISPLAY "Student: " STUDENT-NAME
           DISPLAY "Total Marks: " TOTAL-MARKS
           DISPLAY "Average: " AVERAGE-MARKS

           IF AVERAGE-MARKS >= 40
               DISPLAY "Status: PASS"
           ELSE
               DISPLAY "Status: FAIL"
           END-IF

           STOP RUN.
