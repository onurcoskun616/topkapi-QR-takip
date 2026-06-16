import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useAuth } from "../auth";

export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async () => {
    if (!email || !password) {
      setError("E-posta ve şifre gereklidir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (e) {
      setError(e.message || "Giriş başarısız.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.card}>
        <Text style={styles.title}>Topkapı Okulları</Text>
        <Text style={styles.subtitle}>Personel Yoklama Girişi</Text>

        <TextInput
          style={styles.input}
          placeholder="E-posta"
          placeholderTextColor="#9fb3d1"
          autoCapitalize="none"
          keyboardType="email-address"
          autoComplete="email"
          value={email}
          onChangeText={setEmail}
          editable={!busy}
        />
        <TextInput
          style={styles.input}
          placeholder="Şifre"
          placeholderTextColor="#9fb3d1"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
          editable={!busy}
        />

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <TouchableOpacity
          style={[styles.button, busy && styles.buttonDisabled]}
          onPress={onSubmit}
          disabled={busy}
        >
          {busy ? (
            <ActivityIndicator color="#0b1f3a" />
          ) : (
            <Text style={styles.buttonText}>Giriş Yap</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0b1f3a",
    justifyContent: "center",
    padding: 24,
  },
  card: {
    backgroundColor: "#13325c",
    borderRadius: 20,
    padding: 28,
  },
  title: {
    color: "#fff",
    fontSize: 26,
    fontWeight: "700",
    textAlign: "center",
  },
  subtitle: {
    color: "#9fb3d1",
    fontSize: 15,
    textAlign: "center",
    marginTop: 4,
    marginBottom: 24,
  },
  input: {
    backgroundColor: "#0b1f3a",
    color: "#fff",
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: "#244a82",
  },
  error: {
    color: "#ff8a8a",
    marginBottom: 12,
    textAlign: "center",
  },
  button: {
    backgroundColor: "#ffc83d",
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: "center",
    marginTop: 4,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: {
    color: "#0b1f3a",
    fontSize: 17,
    fontWeight: "700",
  },
});
