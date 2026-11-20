import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Compact blue-and-red identity mark used across the app.
class DigitalDiaryMark extends StatelessWidget {
  final double size;
  const DigitalDiaryMark({super.key, this.size = 48});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        gradient: AppTheme.primaryGradient,
        borderRadius: BorderRadius.circular(size * .28),
        border: Border.all(color: Colors.white.withValues(alpha: .16)),
        boxShadow: [
          BoxShadow(
            color: AppTheme.indigoPrime.withValues(alpha: .24),
            blurRadius: size * .34,
            offset: Offset(0, size * .08),
          ),
        ],
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Icon(Icons.shield_outlined, size: size * .76, color: Colors.white.withValues(alpha: .92)),
          Icon(Icons.menu_book_rounded, size: size * .40, color: Colors.white),
          Positioned(
            right: size * .15,
            top: size * .14,
            child: Container(
              width: size * .12,
              height: size * .12,
              decoration: const BoxDecoration(color: AppTheme.crimsonBadge, shape: BoxShape.circle),
            ),
          ),
        ],
      ),
    );
  }
}
