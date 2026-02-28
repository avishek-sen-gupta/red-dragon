object M {
    def leapYear(year: Int): Int = {
        if (year % 400 == 0) {
            return 1
        }
        if (year % 100 == 0) {
            return 0
        }
        if (year % 4 == 0) {
            return 1
        }
        return 0
    }

    val answer = leapYear(2000)
}
