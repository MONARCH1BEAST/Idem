import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;
import java.util.Scanner;

class Main {
    private static String display(BigDecimal value) {
        DecimalFormat format = new DecimalFormat("0000000.00", DecimalFormatSymbols.getInstance(Locale.ROOT));
        format.setGroupingUsed(false);
        format.setRoundingMode(RoundingMode.DOWN);
        return format.format(value.setScale(2, RoundingMode.DOWN));
    }

    public static void main(String[] args) {
        Scanner input = new Scanner(System.in);
        BigDecimal principal = new BigDecimal(input.nextLine().trim());
        BigDecimal rate = new BigDecimal(input.nextLine().trim());
        int term = Integer.parseInt(input.nextLine().trim());
        BigDecimal interest = principal.multiply(rate)
                .divide(BigDecimal.valueOf(100))
                .multiply(BigDecimal.valueOf(term))
                .divide(BigDecimal.valueOf(12), 2, RoundingMode.HALF_UP);
        BigDecimal total = principal.add(interest).setScale(2, RoundingMode.DOWN);
        System.out.println("INTEREST=" + display(interest));
        System.out.println("TOTAL=" + display(total));
    }
}