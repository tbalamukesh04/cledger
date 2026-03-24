import '../models/transaction.dart';
import '../services/api_service.dart';

class TransactionRepository {
    final ApiService apiService;

    TransactionRepository({required this.apiService});
    
}