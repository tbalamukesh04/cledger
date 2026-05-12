import 'package:flutter/material.dart';

enum LoadingStateType {
  centered,
  inline,
  pagination,
}

class CustomLoadingState extends StatelessWidget {
  final LoadingStateType type;
  final String? message;

  const CustomLoadingState({
    super.key,
    this.type = LoadingStateType.centered,
    this.message,
  });

  const CustomLoadingState.centered({
    super.key,
    this.message,
  }) : type = LoadingStateType.centered;

  const CustomLoadingState.inline({
    super.key,
  }) : type = LoadingStateType.inline,
       message = null;

  const CustomLoadingState.pagination({
    super.key,
  }) : type = LoadingStateType.pagination,
       message = null;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    switch (type) {
      case LoadingStateType.inline:
        return const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(
            strokeWidth: 2.0,
          ),
        );

      case LoadingStateType.pagination:
        return const SafeArea(
          top: false,
          child: Padding(
            padding: EdgeInsets.all(16.0),
            child: Center(
              child: CircularProgressIndicator(),
            ),
          ),
        );

      case LoadingStateType.centered:
      default:
        return Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const CircularProgressIndicator(),
              if (message != null && message!.trim().isNotEmpty) ...[
                const SizedBox(height: 16),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0),
                  child: Text(
                    message!,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.textTheme.bodySmall?.color,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
            ],
          ),
        );
    }
  }
}
