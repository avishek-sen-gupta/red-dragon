class M {
    static String reverseString(String s, int n) {
        String result = "";
        int i = n - 1;
        while (i >= 0) {
            result = result + s[i];
            i = i - 1;
        }
        return result;
    }

    static String answer = reverseString("robot", 5);
}
