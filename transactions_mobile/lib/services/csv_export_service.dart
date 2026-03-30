import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:transactions_mobile/services/api_client.dart';

class CsvExportService {
  final ApiClient apiClient;

  CsvExportService(this.apiClient);

  /// Requests the CSV from the backend and saves it directly to the device's Downloads directory.
  /// Returns the absolute path to the saved CSV file.
  Future<String> exportAndSaveCsv() async {
    // 1. Get the OS-specific Downloads directory
    Directory? directory = await getDownloadsDirectory();
    
    // Fallback to Documents if Downloads isn't accessible on the current OS
    directory ??= await getApplicationDocumentsDirectory();
    
    // 2. Generate a unique filename using a timestamp
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-').split('.').first;
    final savePath = '${directory.path}/transactions_$timestamp.csv';

    // 3. Stream the file directly to storage
    await apiClient.exportTransactions(savePath);

    return savePath;
  }
}