import 'package:flutter/material.dart';

class AppTheme {
  // ── Digital Diary professional palette ───────────────────────────────────
  static const Color navyDeep    = Color(0xFF0B1220);
  static const Color indigoPrime = Color(0xFF2563EB);
  static const Color indigoLight = Color(0xFF60A5FA);
  static const Color goldAccent  = Color(0xFFF4B942);
  static const Color tealAccent  = Color(0xFF14B8A6);
  static const Color crimsonBadge= Color(0xFFE63946);  // alert red
  static const Color surfaceCard = Color(0xFF111C2E);
  static const Color surfaceElevated = Color(0xFF1A2940);
  static const Color textWhite   = Color(0xFFF1F5F9);
  static const Color textSoft    = Color(0xFFAAB7C8);
  static const Color diaryBg     = Color(0xFF101B2B);
  static const Color greenVerified = Color(0xFF06D6A0);

  // ── Gradient helpers ────────────────────────────────────────────────────
  static const LinearGradient primaryGradient = LinearGradient(
    colors: [Color(0xFF1D4ED8), Color(0xFFB42338)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient goldGradient = LinearGradient(
    colors: [Color(0xFFFFB703), Color(0xFFFD9B01)],
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
  );

  static const LinearGradient tealGradient = LinearGradient(
    colors: [tealAccent, Color(0xFF0097A7)],
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
  );

  static const LinearGradient bgGradient = LinearGradient(
    colors: [navyDeep, Color(0xFF10203A), Color(0xFF1A1C32)],
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
  );

  static ThemeData get theme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: navyDeep,
      colorScheme: const ColorScheme.dark(
        primary: indigoPrime,
        secondary: tealAccent,
        tertiary: goldAccent,
        surface: surfaceCard,
        onPrimary: textWhite,
        onSurface: textWhite,
        error: crimsonBadge,
      ),
      textTheme: const TextTheme(
        displayLarge: TextStyle(color: textWhite, fontSize: 28, fontWeight: FontWeight.w900, letterSpacing: -0.5),
        displayMedium: TextStyle(color: textWhite, fontSize: 22, fontWeight: FontWeight.bold),
        titleLarge: TextStyle(color: textWhite, fontSize: 20, fontWeight: FontWeight.bold),
        titleMedium: TextStyle(color: textWhite, fontSize: 16, fontWeight: FontWeight.w600),
        titleSmall: TextStyle(color: textSoft, fontSize: 14, fontWeight: FontWeight.w500),
        bodyLarge: TextStyle(color: textWhite, fontSize: 15),
        bodyMedium: TextStyle(color: textSoft, fontSize: 13),
        bodySmall: TextStyle(color: textSoft, fontSize: 12),
        labelLarge: TextStyle(color: textWhite, fontSize: 14, fontWeight: FontWeight.bold, letterSpacing: 0.5),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: surfaceCard,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: textWhite,
          fontSize: 18,
          fontWeight: FontWeight.bold,
          letterSpacing: 0.3,
        ),
        iconTheme: IconThemeData(color: textWhite),
      ),
      cardTheme: CardThemeData(
        color: surfaceCard,
        elevation: 8,
        shadowColor: Colors.black54,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: indigoPrime.withValues(alpha: 0.3), width: 1),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: indigoPrime,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, letterSpacing: 0.5),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          elevation: 4,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: tealAccent,
          side: const BorderSide(color: tealAccent, width: 1.5),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceElevated,
        labelStyle: const TextStyle(color: textSoft),
        hintStyle: TextStyle(color: textSoft.withValues(alpha: 0.6)),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: indigoPrime, width: 1),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: indigoPrime.withValues(alpha: 0.4), width: 1),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: tealAccent, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: goldAccent,
        foregroundColor: navyDeep,
        elevation: 8,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: surfaceElevated,
        labelStyle: const TextStyle(color: textWhite, fontSize: 11),
        side: BorderSide(color: indigoPrime.withValues(alpha: 0.5)),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: surfaceElevated,
        contentTextStyle: const TextStyle(color: textWhite),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        behavior: SnackBarBehavior.floating,
      ),
      dividerTheme: DividerThemeData(color: indigoPrime.withValues(alpha: 0.3), thickness: 1),
    );
  }
}
