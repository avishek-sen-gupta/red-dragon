<?php
function leapYear($year) {
    if ($year % 400 == 0) {
        return 1;
    }
    if ($year % 100 == 0) {
        return 0;
    }
    if ($year % 4 == 0) {
        return 1;
    }
    return 0;
}

$answer = leapYear(2000);
?>
