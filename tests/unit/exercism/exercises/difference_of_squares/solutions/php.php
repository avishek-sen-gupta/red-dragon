<?php
function squareOfSum($n) {
    $total = 0;
    $i = 1;
    while ($i <= $n) {
        $total = $total + $i;
        $i = $i + 1;
    }
    return $total * $total;
}

function sumOfSquares($n) {
    $total = 0;
    $i = 1;
    while ($i <= $n) {
        $total = $total + $i * $i;
        $i = $i + 1;
    }
    return $total;
}

function differenceOfSquares($n) {
    return squareOfSum($n) - sumOfSquares($n);
}

$answer = differenceOfSquares(10);
?>
