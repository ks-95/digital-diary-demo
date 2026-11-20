import 'package:flutter/material.dart';

class ResponsiveCaseLayout extends StatelessWidget {
  final Widget mobileView;
  final Widget webView;

  const ResponsiveCaseLayout({
    super.key,
    required this.mobileView,
    required this.webView,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Switches to web view if screen width exceeds 900px
        if (constraints.maxWidth > 900) {
          return webView;
        } else {
          return mobileView;
        }
      },
    );
  }
}
