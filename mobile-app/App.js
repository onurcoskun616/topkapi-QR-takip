import { ActivityIndicator, StyleSheet, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { AuthProvider, useAuth } from "./src/auth";
import LoginScreen from "./src/screens/LoginScreen";
import ScannerScreen from "./src/screens/ScannerScreen";

function Root() {
  const { isAuthed, loading } = useAuth();

  if (loading) {
    return (
      <View style={styles.splash}>
        <ActivityIndicator size="large" color="#ffc83d" />
      </View>
    );
  }

  return isAuthed ? <ScannerScreen /> : <LoginScreen />;
}

export default function App() {
  return (
    <AuthProvider>
      <StatusBar style="light" />
      <Root />
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    backgroundColor: "#0b1f3a",
    alignItems: "center",
    justifyContent: "center",
  },
});
